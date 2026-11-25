"""Shared SSRF protection and safe outbound HTTP utilities (IPv4 + IPv6 + redirect validation)."""
import ipaddress
import socket
import urllib.parse
import urllib.request
from typing import Iterable, Optional, Tuple


_EXTRA_BLOCKED_NETWORKS = (
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('100.64.0.0/10'),     # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network('169.254.0.0/16'),    # Link-local / Cloud metadata
    ipaddress.ip_network('192.0.0.0/24'),
    ipaddress.ip_network('192.0.2.0/24'),
    ipaddress.ip_network('198.18.0.0/15'),
    ipaddress.ip_network('198.51.100.0/24'),
    ipaddress.ip_network('203.0.113.0/24'),
    ipaddress.ip_network('240.0.0.0/4'),
    ipaddress.ip_network('::/128'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),          # Unique local IPv6
    ipaddress.ip_network('fe80::/10'),         # Link-local IPv6
    ipaddress.ip_network('fd00:ec2::254/128'), # AWS IMDSv2 IPv6
)


class SSRFBlockedError(ValueError):
    """Raised when an outbound URL resolves to a disallowed host or IP address."""


def is_ip_publicly_routable(ip_str: str) -> bool:
    """Return True only if ip_str is a valid globally routable public IPv4 or IPv6 address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Unwrap IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1 or ::ffff:169.254.169.254)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    for net in _EXTRA_BLOCKED_NETWORKS:
        if ip.version == net.version and ip in net:
            return False

    return True


def validate_safe_external_url(
    url: str,
    *,
    allowed_schemes: Tuple[str, ...] = ('http', 'https'),
    allow_hostnames: Iterable[str] = (),
) -> Tuple[bool, str]:
    """
    Validate that an external URL uses an allowed scheme and that every DNS-resolved
    IPv4 and IPv6 address is globally routable (unless explicitly allowlisted).
    """
    if not url or not isinstance(url, str):
        return False, 'URL is required.'

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return False, 'Malformed URL.'

    if parsed.scheme.lower() not in allowed_schemes:
        return False, f"Disallowed URL scheme: {parsed.scheme or 'none'}."

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        return False, 'Missing hostname.'

    allowed_set = {h.strip().lower() for h in allow_hostnames if h and str(h).strip()}
    if hostname in allowed_set:
        return True, ''

    if hostname in ('localhost', 'localhost.localdomain', 'metadata.google.internal', 'metadata'):
        return False, f'Disallowed internal hostname: {hostname}.'

    # Direct IP literal check
    try:
        ipaddress.ip_address(hostname)
        if not is_ip_publicly_routable(hostname):
            return False, f'Blocked non-public IP address: {hostname}.'
        return True, ''
    except ValueError:
        pass

    # Resolve all IPv4 and IPv6 addresses via getaddrinfo
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except OSError:
        return False, f'Unable to resolve hostname: {hostname}.'

    if not addr_infos:
        return False, f'No DNS records found for hostname: {hostname}.'

    for info in addr_infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        resolved_ip = sockaddr[0]
        if not is_ip_publicly_routable(resolved_ip):
            return False, f'Hostname {hostname} resolves to non-public IP {resolved_ip}.'

    return True, ''


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, *, allowed_schemes=('http', 'https'), allow_hostnames=(), max_redirects=3):
        super().__init__()
        self._allowed_schemes = allowed_schemes
        self._allow_hostnames = tuple(allow_hostnames)
        self._max_redirects = max_redirects
        self._redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._redirect_count += 1
        if self._redirect_count > self._max_redirects:
            raise SSRFBlockedError('Too many HTTP redirects.')
        abs_url = urllib.parse.urljoin(req.full_url, newurl)
        ok, reason = validate_safe_external_url(
            abs_url,
            allowed_schemes=self._allowed_schemes,
            allow_hostnames=self._allow_hostnames,
        )
        if not ok:
            raise SSRFBlockedError(f'Blocked redirect destination: {reason}')
        # Strip sensitive auth headers when crossing origins
        orig_host = (urllib.parse.urlparse(req.full_url).hostname or '').lower()
        new_host = (urllib.parse.urlparse(abs_url).hostname or '').lower()
        new_req = super().redirect_request(req, fp, code, msg, headers, abs_url)
        if new_req is not None and orig_host != new_host:
            for hdr in ('Authorization', 'X-Api-Key', 'Cookie'):
                new_req.remove_header(hdr)
        return new_req


def safe_urlopen(
    req_or_url,
    *,
    timeout: int = 15,
    allowed_schemes: Tuple[str, ...] = ('http', 'https'),
    allow_hostnames: Iterable[str] = (),
    max_redirects: int = 3,
):
    """Open an HTTP/HTTPS URL after enforcing SSRF checks on initial and redirected targets."""
    target_url = req_or_url.full_url if isinstance(req_or_url, urllib.request.Request) else str(req_or_url)
    ok, reason = validate_safe_external_url(
        target_url,
        allowed_schemes=allowed_schemes,
        allow_hostnames=allow_hostnames,
    )
    if not ok:
        raise SSRFBlockedError(reason)

    opener = urllib.request.build_opener(
        _SafeRedirectHandler(
            allowed_schemes=allowed_schemes,
            allow_hostnames=allow_hostnames,
            max_redirects=max_redirects,
        )
    )
    return opener.open(req_or_url, timeout=timeout)

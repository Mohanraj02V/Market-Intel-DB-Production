/**
 * Shared frontend HTML & URL sanitization utilities.
 * Blocks XSS payloads (scripts, inline event handlers, javascript:/vbscript:/data:html/svg URIs)
 * while preserving legitimate rich email & signature formatting.
 */

const SAFE_URL_PROTOCOLS = /^(https?:\/\/|mailto:|tel:)/i;
const STRICT_TEMPLATE_PLACEHOLDER = /^\{\{[a-zA-Z0-9_]+\}\}$/;
const SAFE_DATA_IMAGE_URI = /^data:image\/(png|jpe?g|gif|webp);base64,[a-zA-Z0-9+/=\s]+$/i;

export function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]));
}

export function sanitizeUrl(rawUrl, { allowDataImage = false } = {}) {
  const s = String(rawUrl || '').trim();
  if (!s) return '';
  // Reject control chars or embedded newlines used to obfuscate protocols
  const normalized = s.replace(/[\u0000-\u001F\u007F]+/g, '');
  if (STRICT_TEMPLATE_PLACEHOLDER.test(normalized)) {
    return escapeHtml(normalized);
  }
  if (SAFE_URL_PROTOCOLS.test(normalized)) {
    return escapeHtml(normalized);
  }
  if (allowDataImage && SAFE_DATA_IMAGE_URI.test(normalized)) {
    return escapeHtml(normalized);
  }
  return '';
}

export function sanitizeReturnUrl(rawUrl, fallback = '/settings') {
  const s = String(rawUrl || '').trim();
  if (!s) return fallback;
  // Must be an app-relative path starting with single '/' (blocks '//evil.com' and 'https://evil.com')
  if (/^\/(?!\/|\\)/.test(s)) {
    return s;
  }
  return fallback;
}

export function sanitizeHtml(dirtyHtml) {
  if (!dirtyHtml || typeof dirtyHtml !== 'string') return '';

  let html = dirtyHtml;

  // 1. Remove dangerous executable/embedding containers completely
  const blockedTags = ['script', 'iframe', 'object', 'embed', 'applet', 'form', 'base', 'meta', 'link', 'svg', 'math'];
  for (const tag of blockedTags) {
    const pairedRe = new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?<\\/${tag}\\s*>`, 'gi');
    const singleRe = new RegExp(`<${tag}\\b[^>]*\\/?>`, 'gi');
    html = html.replace(pairedRe, '').replace(singleRe, '');
  }

  // 2. Strip inline JavaScript event handlers (onClick, onError, onLoad, etc.)
  html = html.replace(/\s+on[a-z0-9_-]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '');

  // 3. Neutralize dangerous URI schemes in href/src/action/xlink:href/poster attributes
  html = html.replace(
    /\b(href|src|action|xlink:href|poster)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi,
    (match, attr, dVal, sVal, uVal) => {
      const val = (dVal ?? sVal ?? uVal ?? '').trim();
      const compact = val.replace(/[\u0000-\u0020]+/g, '');
      if (/^(javascript|vbscript):/i.test(compact)) {
        return `${attr}=""`;
      }
      if (/^data:/i.test(compact) && !SAFE_DATA_IMAGE_URI.test(val)) {
        return `${attr}=""`;
      }
      return match;
    }
  );

  // 4. Neutralize CSS expression() / javascript: / behavior: inside inline style attributes
  html = html.replace(
    /\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')/gi,
    (match, dVal, sVal) => {
      const styleVal = dVal ?? sVal ?? '';
      const cleaned = styleVal
        .replace(/expression\s*\([^)]*\)/gi, '')
        .replace(/javascript\s*:/gi, '')
        .replace(/vbscript\s*:/gi, '')
        .replace(/behavior\s*:/gi, '')
        .replace(/@import/gi, '');
      return `style="${cleaned.replace(/"/g, '&quot;')}"`;
    }
  );

  return html;
}

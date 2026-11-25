import test from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, sanitizeHtml, sanitizeReturnUrl, sanitizeUrl } from './htmlSanitizer.js';

test('sanitizeUrl blocks javascript: even with template placeholder bypass attempt', () => {
  assert.equal(sanitizeUrl('javascript:alert(1)//{{x}}'), '');
  assert.equal(sanitizeUrl('vbscript:msgbox(1)'), '');
  assert.equal(sanitizeUrl('data:text/html,<script>alert(1)</script>'), '');
  assert.equal(sanitizeUrl('https://example.com/path?a=1'), 'https://example.com/path?a=1');
  assert.equal(sanitizeUrl('mailto:team@example.com'), 'mailto:team@example.com');
  assert.equal(sanitizeUrl('{{website_url}}'), '{{website_url}}');
});

test('sanitizeReturnUrl prevents open redirects', () => {
  assert.equal(sanitizeReturnUrl('/calendar'), '/calendar');
  assert.equal(sanitizeReturnUrl('/settings?tab=meetings'), '/settings?tab=meetings');
  assert.equal(sanitizeReturnUrl('//evil.com/phish', '/settings'), '/settings');
  assert.equal(sanitizeReturnUrl('https://evil.com/phish', '/settings'), '/settings');
  assert.equal(sanitizeReturnUrl('javascript:alert(1)', '/settings'), '/settings');
});

test('sanitizeHtml strips scripts, event handlers, svg, and javascript URLs while keeping rich markup', () => {
  const dirty = `
    <table style="width:100%; background: expression(alert(1))">
      <tr><td><strong>Hello</strong><img src="x" onerror="alert(1)"><a href="javascript:alert(2)">Click</a></td></tr>
    </table>
    <script>alert('xss')</script>
    <svg onload="alert(3)"></svg>
  `;
  const clean = sanitizeHtml(dirty);
  assert.ok(clean.includes('<strong>Hello</strong>'));
  assert.ok(!/script/i.test(clean));
  assert.ok(!/onerror/i.test(clean));
  assert.ok(!/javascript:/i.test(clean));
  assert.ok(!/expression\s*\(/i.test(clean));
  assert.ok(!/<svg/i.test(clean));
});

test('escapeHtml escapes angle brackets and quotes', () => {
  assert.equal(escapeHtml('<img src="x">'), '&lt;img src=&quot;x&quot;&gt;');
});

import React, { useEffect, useRef, useState } from 'react';
import { message, Tooltip } from 'antd';

function maskValue(value) {
  if (!value) return '-';
  return '••••••••';
}

export default function SensitiveValue({ value, tooltip = '悬浮显示，点击复制' }) {
  const [hovered, setHovered] = useState(false);
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);
  const lastCopyAtRef = useRef(0);

  useEffect(() => () => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
    }
  }, []);

  const copyToClipboard = async (text) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
      }
    } catch {
      // Some deployments are not considered secure contexts; fall back below.
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    if (!ok) {
      throw new Error('copy failed');
    }
  };

  const handleCopy = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    if ('button' in event && event.button !== 0) return;
    if (!value) return;
    const now = Date.now();
    if (now - lastCopyAtRef.current < 250) return;
    lastCopyAtRef.current = now;
    try {
      await copyToClipboard(String(value));
      setCopied(true);
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
      }
      timerRef.current = window.setTimeout(() => setCopied(false), 900);
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  };

  const handleKeyDown = async (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    await handleCopy(event);
  };

  return (
    <Tooltip title={copied ? '已复制' : tooltip}>
      <button
        type="button"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        onMouseDown={handleCopy}
        onClick={handleCopy}
        onKeyDown={handleKeyDown}
        disabled={!value}
        aria-label={tooltip}
        title={tooltip}
        className={`sensitive-chip ${hovered ? 'is-revealed' : ''} ${copied ? 'is-copied' : ''}`}
      >
        {hovered ? value || '-' : maskValue(value)}
      </button>
    </Tooltip>
  );
}

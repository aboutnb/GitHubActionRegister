import React, { useState } from 'react';
import { Tooltip, Typography } from 'antd';

function maskValue(value) {
  if (!value) return '-';
  return '••••••••';
}

export default function SensitiveValue({ value, tooltip = '悬浮显示，点击复制' }) {
  const [hovered, setHovered] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 900);
  };

  return (
    <Tooltip title={copied ? '已复制' : tooltip}>
      <Typography.Text
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={handleCopy}
        className={`sensitive-chip ${hovered ? 'is-revealed' : ''} ${copied ? 'is-copied' : ''}`}
        style={{ cursor: value ? 'pointer' : 'default' }}
      >
        {hovered ? value || '-' : maskValue(value)}
      </Typography.Text>
    </Tooltip>
  );
}

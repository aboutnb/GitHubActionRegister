import React from 'react';

function BrandMark({ size = 'md' }) {
  return (
    <span className={`brand-mark brand-mark--${size}`} aria-hidden="true">
      <span className="brand-mark__frame" />
      <span className="brand-mark__beam brand-mark__beam--primary" />
      <span className="brand-mark__beam brand-mark__beam--secondary" />
      <span className="brand-mark__node brand-mark__node--top" />
      <span className="brand-mark__node brand-mark__node--mid" />
      <span className="brand-mark__node brand-mark__node--bottom" />
      <span className="brand-mark__glow" />
    </span>
  );
}

export function BrandLockup({
  size = 'md',
  title = 'GitHub Asset Center',
  subtitle = 'GitHub 资产中控台',
  onClick,
}) {
  const clickable = typeof onClick === 'function';

  return (
    <div
      className={`brand-lockup brand-lockup--${size}${clickable ? ' brand-lockup--clickable' : ''}`}
      onClick={onClick}
    >
      <BrandMark size={size} />
      <div className="brand-lockup__text">
        <strong>{title}</strong>
        {subtitle ? <span>{subtitle}</span> : null}
      </div>
    </div>
  );
}

export default BrandMark;

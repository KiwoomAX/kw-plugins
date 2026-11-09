import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cx } from './cx';

/* primary 는 상대에게 바로 나가는 동작에만 쓴다. 내부 저장은 기본값 outline 을 쓴다. */
export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'outline' | 'ghost';
  size?: 'sm' | 'md';
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'outline', size = 'md', type = 'button', className, ...rest },
  ref,
) {
  return <button ref={ref} type={type} className={cx('kw-btn', `kw-btn--${variant}`, `kw-btn--${size}`, className)} {...rest} />;
});

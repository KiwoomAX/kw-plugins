import { forwardRef, type InputHTMLAttributes } from 'react';
import { cx } from './cx';

/* invalid 를 주면 빨간 테두리로 표시하고 화면 낭독기에도 잘못된 입력으로 알린다. 폭은 부모가 정한다. */
export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid = false, className, ...rest },
  ref,
) {
  return <input ref={ref} aria-invalid={invalid || undefined} className={cx('kw-input', className)} {...rest} />;
});

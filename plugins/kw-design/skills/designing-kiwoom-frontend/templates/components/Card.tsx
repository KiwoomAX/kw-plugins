import type { HTMLAttributes, ReactNode } from 'react';
import { cx } from './cx';

/* 목록 표는 표 자체가 상자이므로 Card 로 감싸지 않는다. */
export type CardProps = Omit<HTMLAttributes<HTMLElement>, 'title'> & {
  title?: ReactNode;
  actions?: ReactNode;
};

export function Card({ title, actions, className, children, ...rest }: CardProps) {
  return (
    <section className={cx('kw-card', className)} {...rest}>
      {(title || actions) && (
        <header className="kw-card__head">
          {title && <h3 className="kw-card__title">{title}</h3>}
          {actions && <div className="kw-card__actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

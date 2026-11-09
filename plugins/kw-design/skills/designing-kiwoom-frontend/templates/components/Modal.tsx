import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

/* 브라우저 기본 대화상자로 연다. 바깥을 눌러도 닫지 않는다. 입력 중인 내용이 사라지기 때문이다. */
export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
};

export function Modal({ open, onClose, title, footer, children }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      className="kw-modal"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      {open && (
        <>
          <header className="kw-modal__head">
            <h2 id={titleId} className="kw-modal__title">{title}</h2>
            <button type="button" className="kw-modal__close" aria-label="닫기" onClick={onClose}>
              <X size={14} strokeWidth={1.7} />
            </button>
          </header>
          <div className="kw-modal__body">{children}</div>
          {footer && <footer className="kw-modal__foot">{footer}</footer>}
        </>
      )}
    </dialog>
  );
}

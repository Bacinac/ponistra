import { X } from 'lucide-react';
import { iconButton } from './styles';

export function RemoveButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={iconButton}
    >
      <X size={16} aria-hidden />
    </button>
  );
}

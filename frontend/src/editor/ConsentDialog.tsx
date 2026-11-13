import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { button, primaryButton } from '../styles';
import type { Consent } from './runs';

/** Asks before a model's action sends its target out: what leaves and where it goes, this once
 * or from now on in the document. */
export function ConsentDialog({
  onChoose,
  onClose,
}: {
  onChoose: (consent: Consent) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal heading={t('ai.consent.heading')} onClose={onClose}>
      <p className="text-sm">{t('ai.consent.body')}</p>
      <p className="text-sm text-muted">{t('ai.consent.note')}</p>
      <div className="flex flex-wrap justify-end gap-2">
        <Cancel />
        <button type="button" className={button} onClick={() => onChoose('always')}>
          {t('ai.consent.always')}
        </button>
        <button type="button" className={primaryButton} onClick={() => onChoose('once')}>
          {t('ai.consent.once')}
        </button>
      </div>
    </Modal>
  );
}

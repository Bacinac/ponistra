import { Close, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { shortcutLabel } from '../keys';
import { GROUPS, inGroup, labelOf } from './commands';

const key = 'rounded border border-line px-1.5 font-sans text-xs';

export function Shortcuts({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  return (
    <Modal heading={t('command.shortcuts')} onClose={onClose}>
      <div className="flex max-h-[60dvh] flex-col gap-4 overflow-y-auto">
        {GROUPS.map((group) => {
          const listed = inGroup(group).filter((command) => command.keys || command.typed);
          if (!listed.length) return null;
          return (
            <section key={group} className="flex flex-col gap-1">
              <h3 className="text-sm font-semibold text-muted">{t(`commandGroup.${group}`)}</h3>
              <dl className="flex flex-col gap-1 text-sm">
                {listed.map((command) => (
                  <div key={command.id} className="flex items-center justify-between gap-4">
                    <dt>{labelOf(command, t)}</dt>
                    <dd className="flex flex-wrap justify-end gap-1">
                      {command.keys?.map((keys) => (
                        <kbd key={keys} className={key}>
                          {shortcutLabel(keys)}
                        </kbd>
                      ))}
                      {command.typed && (
                        <>
                          <kbd className={key}>{command.typed.trim()}</kbd>
                          <kbd className={key}>{t('shortcuts.space')}</kbd>
                        </>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          );
        })}
      </div>
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}

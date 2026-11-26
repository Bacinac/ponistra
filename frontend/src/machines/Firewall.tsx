import { useState, type FormEvent } from 'react';
import { Cancel, Modal, Picker } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, compactField, iconButton, primaryButton } from '../styles';
import {
  guestPath,
  PROTOCOLS,
  RULE_ACTIONS,
  useFirewall,
  useMachineWrite,
  type Firewall as FirewallData,
  type Protocol,
  type Rule,
  type RuleAction,
} from './api';
import { Fact, Facts, Failure, Loaded, Pill, table } from './parts';

type Way = 'ingress' | 'egress';

/** A guest's firewall: what comes in is dropped and what goes out is allowed unless its rules
 * say otherwise; a macvlan or physical NIC carries none. */
export function Firewall({ guest }: { guest: string }) {
  const { t } = useI18n();
  const firewall = useFirewall(guest);
  const [editing, setEditing] = useState(false);
  return (
    <Headed
      heading={t('machine.firewall')}
      action={
        <button
          type="button"
          className={button}
          disabled={!firewall.data}
          onClick={() => setEditing(true)}
        >
          {t('machine.firewall.edit')}
        </button>
      }
    >
      <Loaded query={firewall}>{(data) => <FirewallParts firewall={data} />}</Loaded>
      {editing && firewall.data && (
        <FirewallForm guest={guest} firewall={firewall.data} onClose={() => setEditing(false)} />
      )}
    </Headed>
  );
}

function FirewallParts({ firewall }: { firewall: FirewallData }) {
  const { t } = useI18n();
  const nics = firewall.nics ?? [];
  return (
    <>
      <Facts>
        <Fact label="machine.firewall.ingressDefault">
          {t(`machine.firewall.action.${firewall.ingress_default}`)}
        </Fact>
        <Fact label="machine.firewall.egressDefault">
          {t(`machine.firewall.action.${firewall.egress_default}`)}
        </Fact>
        <Fact label="machine.firewall.nics">
          {nics.length === 0 ? (
            '—'
          ) : (
            <ul className="flex flex-col gap-1">
              {nics.map((nic) => (
                <li key={nic.name} className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs">
                    {nic.name} ({nic.network})
                  </span>
                  <Pill tone={nic.attached ? 'ok' : 'bad'}>
                    {t(nic.attached ? 'machine.firewall.attached' : 'machine.firewall.unattached')}
                  </Pill>
                  {nic.reason && <span className="text-xs text-muted">{nic.reason}</span>}
                </li>
              ))}
            </ul>
          )}
        </Fact>
      </Facts>
      <Rules way="ingress" rules={firewall.ingress ?? []} />
      <Rules way="egress" rules={firewall.egress ?? []} />
    </>
  );
}

function Rules({ way, rules }: { way: Way; rules: Rule[] }) {
  const { t } = useI18n();
  return (
    <section aria-label={t(`machine.firewall.${way}`)} className="flex flex-col gap-1">
      <h3 className="text-sm font-medium">{t(`machine.firewall.${way}`)}</h3>
      {rules.length === 0 ? (
        <p className="text-sm text-muted">{t('machine.firewall.noRules')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={table}>
            <thead>
              <tr>
                <th>{t('machine.firewall.rule.action')}</th>
                <th>{t('machine.firewall.rule.protocol')}</th>
                <th>
                  {t(
                    way === 'ingress'
                      ? 'machine.firewall.rule.source'
                      : 'machine.firewall.rule.destination',
                  )}
                </th>
                <th>{t('machine.firewall.rule.port')}</th>
                <th>{t('machine.firewall.rule.description')}</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule, index) => (
                <tr key={index}>
                  <td>{t(`machine.firewall.action.${rule.action}`)}</td>
                  <td>{rule.protocol || t('machine.firewall.any')}</td>
                  <td className="font-mono text-xs">
                    {(way === 'ingress' ? rule.source : rule.destination) ||
                      t('machine.firewall.any')}
                  </td>
                  <td className="font-mono text-xs">{rule.port || '—'}</td>
                  <td>{rule.description || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const PORTED: Protocol[] = ['tcp', 'udp'];

const blank = (way: Way): Rule => ({
  action: way === 'ingress' ? 'allow' : 'drop',
  protocol: 'tcp',
  port: '',
});

function FirewallForm({
  guest,
  firewall,
  onClose,
}: {
  guest: string;
  firewall: FirewallData;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [ingressDefault, setIngressDefault] = useState(firewall.ingress_default);
  const [egressDefault, setEgressDefault] = useState(firewall.egress_default);
  const [rules, setRules] = useState<Record<Way, Rule[]>>({
    ingress: firewall.ingress ?? [],
    egress: firewall.egress ?? [],
  });
  const save = useMachineWrite(
    (api, body: object) => api.send('PUT', `${guestPath(guest)}/firewall`, body),
    onClose,
  );
  const actions = RULE_ACTIONS.map(
    (action) => [action, t(`machine.firewall.action.${action}`)] as const,
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const cleaned = (list: Rule[], way: Way) =>
      list.map((rule) => {
        const peer = (way === 'ingress' ? rule.source : rule.destination)?.trim();
        const port = PORTED.includes(rule.protocol ?? '') ? rule.port?.trim() : '';
        return {
          action: rule.action,
          ...(rule.protocol && { protocol: rule.protocol }),
          ...(peer && { [way === 'ingress' ? 'source' : 'destination']: peer }),
          ...(port && { port }),
          ...(rule.description?.trim() && { description: rule.description.trim() }),
        };
      });
    save.mutate({
      ingress_default: ingressDefault,
      egress_default: egressDefault,
      ingress: cleaned(rules.ingress, 'ingress'),
      egress: cleaned(rules.egress, 'egress'),
    });
  };

  const editor = (way: Way) => {
    const list = rules[way];
    const set = (index: number, next: Partial<Rule>) =>
      setRules({
        ...rules,
        [way]: list.map((rule, at) => (at === index ? { ...rule, ...next } : rule)),
      });
    const peer = way === 'ingress' ? 'source' : 'destination';
    return (
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{t(`machine.firewall.${way}`)}</legend>
        {list.map((rule, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2">
            <select
              aria-label={t('machine.firewall.rule.action')}
              value={rule.action}
              onChange={(event) => set(index, { action: event.target.value as RuleAction })}
              className={`${compactField} w-28`}
            >
              {actions.map(([action, label]) => (
                <option key={action} value={action}>
                  {label}
                </option>
              ))}
            </select>
            <select
              aria-label={t('machine.firewall.rule.protocol')}
              value={rule.protocol ?? ''}
              onChange={(event) => set(index, { protocol: event.target.value as Protocol })}
              className={`${compactField} w-28`}
            >
              {PROTOCOLS.map((protocol) => (
                <option key={protocol} value={protocol}>
                  {protocol || t('machine.firewall.any')}
                </option>
              ))}
            </select>
            <input
              aria-label={t(`machine.firewall.rule.${peer}`)}
              value={rule[peer] ?? ''}
              placeholder={t(`machine.firewall.rule.${peer}`)}
              onChange={(event) => set(index, { [peer]: event.target.value })}
              spellCheck={false}
              className={`${compactField} min-w-40 flex-1 font-mono`}
            />
            <input
              aria-label={t('machine.firewall.rule.port')}
              value={PORTED.includes(rule.protocol ?? '') ? (rule.port ?? '') : ''}
              placeholder={t('machine.firewall.rule.port')}
              disabled={!PORTED.includes(rule.protocol ?? '')}
              onChange={(event) => set(index, { port: event.target.value })}
              spellCheck={false}
              className={`${compactField} w-28 font-mono`}
            />
            <input
              aria-label={t('machine.firewall.rule.description')}
              value={rule.description ?? ''}
              placeholder={t('machine.firewall.rule.description')}
              onChange={(event) => set(index, { description: event.target.value })}
              className={`${compactField} min-w-40 flex-1`}
            />
            <button
              type="button"
              className={iconButton}
              onClick={() => setRules({ ...rules, [way]: list.filter((_, at) => at !== index) })}
            >
              {t('machine.firewall.rule.remove')}
            </button>
          </div>
        ))}
        <div>
          <button
            type="button"
            className={button}
            onClick={() => setRules({ ...rules, [way]: [...list, blank(way)] })}
          >
            {t('machine.firewall.rule.add')}
          </button>
        </div>
      </fieldset>
    );
  };

  return (
    <Modal wide heading={t('machine.firewall.edit')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid gap-2 sm:grid-cols-2">
          <Picker
            label={t('machine.firewall.ingressDefault')}
            value={ingressDefault}
            options={actions}
            onChange={setIngressDefault}
          />
          <Picker
            label={t('machine.firewall.egressDefault')}
            value={egressDefault}
            options={actions}
            onChange={setEgressDefault}
          />
        </div>
        {editor('ingress')}
        {editor('egress')}
        <Failure error={save.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={save.isPending}>
            {t('machine.firewall.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

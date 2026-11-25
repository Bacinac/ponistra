import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { Alerts } from './Alerts';
import type { MessageKey } from '../i18n/hr';
import {
  useAgent,
  useHealth,
  useMachine,
  useResources,
  type Health,
  type HealthState,
  type Machine,
  type Resource,
  type Resources,
} from './api';
import {
  card,
  Fact,
  Facts,
  Failure,
  Loaded,
  Meter,
  Pill,
  table,
  useFormats,
  type Tone,
} from './parts';

const STALLS: { resource: Resource; kind: 'some' | 'full'; label: MessageKey }[] = [
  { resource: 'cpu', kind: 'some', label: 'machine.psi.cpu.some' },
  { resource: 'memory', kind: 'some', label: 'machine.psi.memory.some' },
  { resource: 'memory', kind: 'full', label: 'machine.psi.memory.full' },
  { resource: 'io', kind: 'some', label: 'machine.psi.io.some' },
  { resource: 'io', kind: 'full', label: 'machine.psi.io.full' },
];

const HEALTH_TONES: Record<HealthState, Tone> = {
  green: 'ok',
  red: 'bad',
  checking: 'quiet',
  waiting: 'quiet',
};

export function HealthPill({ state }: { state: HealthState }) {
  const { t } = useI18n();
  return <Pill tone={HEALTH_TONES[state]}>{t(`machine.health.${state}`)}</Pill>;
}

export function Overview() {
  const machine = useMachine();
  const health = useHealth();
  const resources = useResources();
  return (
    <div className="flex flex-col gap-6">
      <Alerts />
      <Loaded query={health}>{(data) => <HealthPart health={data} />}</Loaded>
      <Loaded query={machine}>{(data) => <MachinePart machine={data} />}</Loaded>
      <Loaded query={resources}>{(data) => <ResourcesPart resources={data} />}</Loaded>
    </div>
  );
}

function HealthPart({ health }: { health: Health }) {
  const { t } = useI18n();
  return (
    <section className={card} aria-label={t('machine.health')}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{t('machine.health')}</h2>
        <HealthPill state={health.state} />
      </div>
      {health.faults.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {health.faults.map((fault) => (
            <li key={fault.name}>
              <span className="font-medium">{fault.name}</span>
              <span className="text-muted"> · {fault.text}</span>
            </li>
          ))}
        </ul>
      )}
      {health.failed_units.length > 0 && (
        <div className="flex flex-col gap-1 text-sm">
          <h3 className="text-muted">{t('machine.health.failedUnits')}</h3>
          <ul className="flex flex-wrap gap-1.5">
            {health.failed_units.map((unit) => (
              <li key={unit}>
                <Pill tone="bad">{unit}</Pill>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function MachinePart({ machine }: { machine: Machine }) {
  const { t } = useI18n();
  const format = useFormats();
  const agent = useAgent();
  const { os, hardware, security } = machine;
  const secureBoot =
    security.secure_boot === null
      ? 'machine.secureBoot.legacy'
      : security.secure_boot
        ? 'machine.secureBoot.on'
        : 'machine.secureBoot.off';
  return (
    <Headed heading={t('machine.machine')}>
      <Facts>
        <Fact label="machine.hostname">{machine.hostname}</Fact>
        <Fact label="machine.os">
          {os.name} {os.version} · {t(`machine.variant.${os.variant}`)}
        </Fact>
        <Fact label="machine.image">{os.image}</Fact>
        <Fact label="machine.kernel">{os.kernel}</Fact>
        <Fact label="machine.agent">{agent.data?.version ?? <Failure error={agent.error} />}</Fact>
        <Fact label="machine.bootedAt">{format.date(machine.booted_at)}</Fact>
        <Fact label="machine.hardware">
          {[hardware.vendor, hardware.product, hardware.version].filter(Boolean).join(' ')}
        </Fact>
        {hardware.serial && <Fact label="machine.serial">{hardware.serial}</Fact>}
        <Fact label="machine.cpu">
          {hardware.cpu} · {format.number(hardware.cpus)} {t('machine.cores')}
        </Fact>
        <Fact label="machine.memory">{format.bytes(hardware.memory)}</Fact>
        <Fact label="machine.secureBoot">{t(secureBoot)}</Fact>
        <Fact label="machine.tpm">{security.tpm || t('machine.tpm.none')}</Fact>
      </Facts>
    </Headed>
  );
}

function ResourcesPart({ resources }: { resources: Resources }) {
  const { t } = useI18n();
  const format = useFormats();
  const { memory } = resources;
  const used = memory.total - memory.available;
  const swapUsed = memory.swap_total - memory.swap_free;
  return (
    <Headed heading={t('machine.resources')}>
      <Facts>
        <Fact label="machine.load">
          {resources.load.map((each) => format.number(each)).join(' · ')}
        </Fact>
        <Fact label="machine.memory">
          <Meter share={(used / memory.total) * 100} label={t('machine.memory')} />
          <span className="text-xs text-muted">
            {format.bytes(used)} / {format.bytes(memory.total)}
          </span>
        </Fact>
        {memory.swap_total > 0 && (
          <Fact label="machine.swap">
            <Meter share={(swapUsed / memory.swap_total) * 100} label={t('machine.swap')} />
            <span className="text-xs text-muted">
              {format.bytes(swapUsed)} / {format.bytes(memory.swap_total)}
            </span>
          </Fact>
        )}
      </Facts>
      <table className={table}>
        <thead>
          <tr>
            <th>{t('machine.pressure.now')}</th>
            <th>10 s</th>
            <th>60 s</th>
            <th>300 s</th>
          </tr>
        </thead>
        <tbody>
          {STALLS.map(({ resource, kind, label }) => {
            const stall = resources.pressure[resource]?.[kind];
            if (!stall) return null;
            return (
              <tr key={label}>
                <td>{t(label)}</td>
                <td className="tabular-nums">{format.percent(stall.avg10)}</td>
                <td className="tabular-nums">{format.percent(stall.avg60)}</td>
                <td className="tabular-nums">{format.percent(stall.avg300)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <table className={table}>
        <thead>
          <tr>
            <th>{t('machine.filesystem')}</th>
            <th className="w-1/2">{t('machine.used')}</th>
            <th>{t('machine.free')}</th>
          </tr>
        </thead>
        <tbody>
          {resources.filesystems.map((each) => (
            <tr key={each.path}>
              <td className="font-mono text-xs">{each.path}</td>
              <td>
                <Meter share={((each.size - each.avail) / each.size) * 100} label={each.path} />
              </td>
              <td className="tabular-nums">
                {format.bytes(each.avail)} / {format.bytes(each.size)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className={table}>
        <thead>
          <tr>
            <th>{t('machine.interface')}</th>
            <th>{t('machine.state')}</th>
            <th>{t('machine.addresses')}</th>
          </tr>
        </thead>
        <tbody>
          {resources.interfaces.map((each) => (
            <tr key={each.name}>
              <td>
                <span className="font-mono text-xs">{each.name}</span>
                <span className="block text-xs text-muted">
                  {each.kind}
                  {each.mac && ` · ${each.mac}`}
                </span>
              </td>
              <td>
                <Pill tone={each.state === 'up' ? 'ok' : 'quiet'}>{each.state}</Pill>
                {each.speed ? (
                  <span className="ml-2 text-xs text-muted">{format.number(each.speed)} Mb/s</span>
                ) : null}
              </td>
              <td className="font-mono text-xs">{each.addresses.join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Headed>
  );
}

import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { useHardware, usePools, type HardwareState } from './api';
import { Loaded, Meter, Pill, table, useFormats } from './parts';

export function Hardware({ pools }: { pools: boolean }) {
  const hardware = useHardware();
  return (
    <div className="flex flex-col gap-6">
      <Loaded query={hardware}>{(data) => <HardwareParts hardware={data} />}</Loaded>
      {pools && <Pools />}
    </div>
  );
}

function HardwareParts({ hardware }: { hardware: HardwareState }) {
  const { t } = useI18n();
  const format = useFormats();
  return (
    <>
      {hardware.errors.length > 0 && (
        <section
          role="alert"
          aria-label={t('machine.hardware.unread')}
          className="flex flex-col gap-1 text-sm"
        >
          <h2 className="font-semibold text-danger">{t('machine.hardware.unread')}</h2>
          <ul className="list-inside list-disc text-danger">
            {hardware.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </section>
      )}
      <Headed heading={t('machine.disks')}>
        <div className="overflow-x-auto">
          <table className={table}>
            <thead>
              <tr>
                <th>{t('machine.disk')}</th>
                <th>{t('machine.size')}</th>
                <th>SMART</th>
                <th>{t('machine.temperature')}</th>
                <th>{t('machine.disk.wear')}</th>
              </tr>
            </thead>
            <tbody>
              {hardware.disks.map((disk) => {
                const { smart } = disk;
                const wear = [
                  smart.power_on_hours !== undefined && `${format.number(smart.power_on_hours)} h`,
                  smart.percent_used !== undefined &&
                    `${format.percent(smart.percent_used)} ${t('machine.disk.used')}`,
                  smart.media_errors &&
                    `${format.number(smart.media_errors)} ${t('machine.disk.mediaErrors')}`,
                  smart.reallocated_sectors &&
                    `${format.number(smart.reallocated_sectors)} ${t('machine.disk.reallocated')}`,
                  smart.pending_sectors &&
                    `${format.number(smart.pending_sectors)} ${t('machine.disk.pending')}`,
                ].filter(Boolean);
                return (
                  <tr key={disk.name}>
                    <td>
                      <span className="font-mono text-xs">{disk.name}</span>
                      <span className="block text-xs text-muted">
                        {[disk.model, disk.transport, disk.rotational ? t('machine.disk.hdd') : '']
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </td>
                    <td className="tabular-nums">{format.bytes(disk.size)}</td>
                    <td>
                      {smart.error ? (
                        <span className="text-xs text-danger">{smart.error}</span>
                      ) : smart.passed === null ? (
                        <Pill tone="quiet">{t('machine.smart.unknown')}</Pill>
                      ) : (
                        <Pill tone={smart.passed ? 'ok' : 'bad'}>
                          {t(smart.passed ? 'machine.smart.passed' : 'machine.smart.failed')}
                        </Pill>
                      )}
                    </td>
                    <td className="tabular-nums">
                      {smart.temperature !== undefined
                        ? `${format.number(smart.temperature)} °C`
                        : '—'}
                    </td>
                    <td className="text-xs">{wear.join(' · ') || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Headed>
      {hardware.pools && hardware.pools.length > 0 && (
        <Headed heading={t('machine.pools.state')}>
          <table className={table}>
            <thead>
              <tr>
                <th>{t('machine.pool')}</th>
                <th>{t('machine.state')}</th>
                <th>{t('machine.pool.errors')}</th>
                <th>{t('machine.pool.scrub')}</th>
              </tr>
            </thead>
            <tbody>
              {hardware.pools.map((pool) => {
                const errors = pool.read_errors + pool.write_errors + pool.checksum_errors;
                return (
                  <tr key={pool.name}>
                    <td>{pool.name}</td>
                    <td>
                      <Pill tone={pool.state === 'ONLINE' ? 'ok' : 'bad'}>{pool.state}</Pill>
                    </td>
                    <td className={`tabular-nums ${errors ? 'text-danger' : ''}`}>
                      {format.number(pool.read_errors)} / {format.number(pool.write_errors)} /{' '}
                      {format.number(pool.checksum_errors)}
                    </td>
                    <td className="text-xs">
                      {pool.scrub ? (
                        <>
                          {t(`machine.scrub.${pool.scrub.state}`)}{' '}
                          {format.date(pool.scrub.ended_at ?? pool.scrub.started_at)}
                          {pool.scrub.errors > 0 && (
                            <span className="text-danger">
                              {' '}
                              · {format.number(pool.scrub.errors)} {t('machine.pool.errors')}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-muted">{t('machine.scrub.never')}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Headed>
      )}
      {hardware.temperatures.length > 0 && (
        <Headed heading={t('machine.temperatures')}>
          <table className={table}>
            <thead>
              <tr>
                <th>{t('machine.sensor')}</th>
                <th>{t('machine.temperature')}</th>
                <th>{t('machine.critical')}</th>
              </tr>
            </thead>
            <tbody>
              {hardware.temperatures.map((each) => (
                <tr key={`${each.sensor}-${each.label}`}>
                  <td>
                    {each.label || each.sensor}
                    {each.label && <span className="ml-2 text-xs text-muted">{each.sensor}</span>}
                  </td>
                  <td
                    className={`tabular-nums ${each.critical !== undefined && each.celsius >= each.critical - 5 ? 'text-danger' : ''}`}
                  >
                    {format.number(each.celsius)} °C
                  </td>
                  <td className="tabular-nums text-muted">
                    {each.critical !== undefined ? `${format.number(each.critical)} °C` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Headed>
      )}
      {hardware.batteries.length > 0 && (
        <Headed heading={t('machine.batteries')}>
          <table className={table}>
            <thead>
              <tr>
                <th>{t('machine.battery')}</th>
                <th className="w-1/3">{t('machine.battery.charge')}</th>
                <th>{t('machine.battery.health')}</th>
                <th>{t('machine.battery.cycles')}</th>
              </tr>
            </thead>
            <tbody>
              {hardware.batteries.map((battery) => (
                <tr key={battery.name}>
                  <td>
                    {battery.name}
                    <span className="ml-2 text-xs text-muted">{battery.status}</span>
                  </td>
                  <td>
                    <Meter share={battery.capacity} label={battery.name} />
                  </td>
                  <td className="tabular-nums">
                    {battery.health !== undefined ? format.percent(battery.health) : '—'}
                  </td>
                  <td className="tabular-nums">
                    {battery.cycles !== undefined ? format.number(battery.cycles) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Headed>
      )}
    </>
  );
}

function Pools() {
  const { t } = useI18n();
  const format = useFormats();
  const pools = usePools();
  return (
    <Headed heading={t('machine.pools')}>
      <Loaded query={pools}>
        {(data) => (
          <table className={table}>
            <thead>
              <tr>
                <th>{t('machine.pool')}</th>
                <th>{t('machine.state')}</th>
                <th className="w-1/3">{t('machine.used')}</th>
                <th>{t('machine.free')}</th>
                <th>{t('machine.pool.fragmentation')}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((pool) => (
                <tr key={pool.name}>
                  <td>{pool.name}</td>
                  <td>
                    <Pill tone={pool.health === 'ONLINE' ? 'ok' : 'bad'}>{pool.health}</Pill>
                  </td>
                  <td>
                    <Meter share={pool.capacity} label={pool.name} />
                  </td>
                  <td className="tabular-nums">
                    {format.bytes(pool.free)} / {format.bytes(pool.size)}
                  </td>
                  <td className="tabular-nums">{format.percent(pool.fragmentation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Loaded>
    </Headed>
  );
}

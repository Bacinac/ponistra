import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { CALENDAR, RESOURCE_KINDS, type Resource } from './calendarData';
import { Cancel, ConfirmDialog, Modal, Picker } from './dialogs';
import { Loaded, PrimaryAction } from './frame';
import { SettingsFrame } from './settings';
import { useI18n } from './i18n';
import { field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';

const RESOURCES = [...CALENDAR, 'resources'];

type Dialog = { type: 'edit'; resource?: Resource } | { type: 'delete'; resource: Resource };

function useResourceChange<V>(mutationFn: (variables: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CALENDAR }),
  });
}

function ResourceDialog({ resource, onClose }: { resource?: Resource; onClose: () => void }) {
  const { t } = useI18n();
  const [form, setForm] = useState({
    name: resource?.name ?? '',
    kind: resource?.kind ?? ('room' as Resource['kind']),
    capacity: resource?.capacity ? String(resource.capacity) : '',
    place: resource?.place ?? '',
    active: resource?.active ?? true,
  });
  const save = useResourceChange(() => {
    const body = {
      name: form.name.trim(),
      kind: form.kind,
      capacity: form.capacity === '' ? null : Number(form.capacity),
      place: form.place.trim(),
      active: form.active,
    };
    return resource
      ? patchJson(`/api/calendar/resources/${resource.id}`, body)
      : postJson('/api/calendar/resources', body);
  });
  const set = (changes: Partial<typeof form>) => setForm({ ...form, ...changes });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: onClose });
  }

  return (
    <Modal heading={t(resource ? 'resources.edit' : 'resources.new')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('resources.name')}
          <input
            type="text"
            required
            maxLength={200}
            value={form.name}
            onChange={(event) => set({ name: event.target.value })}
            className={field}
          />
        </label>
        <Picker
          label={t('resources.kind')}
          value={form.kind}
          options={RESOURCE_KINDS.map((each) => [each, t(`resources.kind.${each}`)] as const)}
          onChange={(kind) => set({ kind })}
        />
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('resources.capacity')}
            <input
              type="number"
              min={0}
              max={100000}
              value={form.capacity}
              onChange={(event) => set({ capacity: event.target.value })}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('resources.place')}
            <input
              type="text"
              maxLength={200}
              value={form.place}
              onChange={(event) => set({ place: event.target.value })}
              className={field}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(event) => set({ active: event.target.checked })}
          />
          {t('resources.active')}
        </label>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(resource ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Inventory({ resources }: { resources: Resource[] }) {
  const { t, formatNumber } = useI18n();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const remove = useResourceChange((resource: Resource) =>
    deleteJson(`/api/calendar/resources/${resource.id}`),
  );
  const close = () => setDialog(null);
  const cell = 'px-2 py-2 whitespace-nowrap';
  return (
    <SettingsFrame
      title={t('resources.title')}
      primary={
        <PrimaryAction
          icon={Plus}
          label={t('resources.new')}
          onClick={() => setDialog({ type: 'edit' })}
        />
      }
    >
      <div className="flex w-full max-w-5xl flex-col gap-4">
        <p className="text-sm text-muted">{t('resources.note')}</p>
        {remove.isError && <p className="text-sm text-danger">{errorMessage(remove.error, t)}</p>}
        {resources.length === 0 ? (
          <p className="text-sm text-muted">{t('resources.none')}</p>
        ) : (
          <table className="w-full border-collapse">
            <thead className="text-left text-sm text-muted">
              <tr className="border-b border-line">
                <th className="w-full px-2 py-2 font-normal">{t('resources.name')}</th>
                <th className="px-2 py-2 font-normal">{t('resources.kind')}</th>
                <th className="hidden px-2 py-2 font-normal sm:table-cell">
                  {t('resources.capacity')}
                </th>
                <th className="hidden px-2 py-2 font-normal md:table-cell">
                  {t('resources.place')}
                </th>
                <th className="w-20" />
              </tr>
            </thead>
            <tbody>
              {resources.map((resource) => (
                <tr
                  key={resource.id}
                  className={`border-b border-line ${resource.active ? '' : 'text-muted'}`}
                >
                  <td className={cell}>
                    {resource.name}
                    {!resource.active && (
                      <span className="ml-2 text-xs">({t('resources.retired')})</span>
                    )}
                  </td>
                  <td className={cell}>{t(`resources.kind.${resource.kind}`)}</td>
                  <td className={`${cell} hidden sm:table-cell`}>
                    {resource.capacity ? formatNumber(resource.capacity) : ''}
                  </td>
                  <td className={`${cell} hidden md:table-cell`}>{resource.place}</td>
                  <td className={`${cell} text-right`}>
                    <button
                      type="button"
                      onClick={() => setDialog({ type: 'edit', resource })}
                      aria-label={`${t('resources.edit')}: ${resource.name}`}
                      className={iconButton}
                    >
                      <Pencil size={16} aria-hidden />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDialog({ type: 'delete', resource })}
                      aria-label={`${t('resources.delete')}: ${resource.name}`}
                      className={iconButton}
                    >
                      <Trash2 size={16} aria-hidden />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {dialog?.type === 'edit' && <ResourceDialog resource={dialog.resource} onClose={close} />}
      {dialog?.type === 'delete' && (
        <ConfirmDialog
          heading={t('resources.deleteTitle')}
          confirmLabel={t('resources.delete')}
          onConfirm={() => remove.mutate(dialog.resource, { onSuccess: close })}
          onClose={close}
        >
          <strong>{dialog.resource.name}</strong> {t('resources.deleteWarning')}
        </ConfirmDialog>
      )}
    </SettingsFrame>
  );
}

export function ResourcesPage() {
  const me = useSession().data?.user;
  const resources = useQuery({
    queryKey: RESOURCES,
    queryFn: () => getJson<{ resources: Resource[] }>('/api/calendar/resources'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return <Loaded query={resources}>{(data) => <Inventory resources={data.resources} />}</Loaded>;
}

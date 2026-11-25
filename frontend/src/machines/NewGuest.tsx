import { useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import {
  CLASSES,
  GROUPS,
  GUEST_NAME,
  useIsos,
  useMachineWrite,
  useNetworks,
  useRecipes,
  type GuestClass,
  type Recipe,
} from './api';
import { Failure, Loaded } from './parts';

/** A guest from a recipe: the catalogue by group first, then the chosen recipe's form. */
export function NewGuest({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const recipes = useRecipes();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  return (
    <Modal wide heading={recipe ? recipe.title : t('machine.guest.new')} onClose={onClose}>
      {recipe ? (
        <RecipeForm recipe={recipe} back={() => setRecipe(null)} onClose={onClose} />
      ) : (
        <Loaded query={recipes}>
          {(list) => (
            <div className="flex flex-col gap-5">
              {GROUPS.map((group) => {
                const members = list.filter((each) => each.group === group);
                if (!members.length) return null;
                return (
                  <section
                    key={group}
                    aria-label={t(`machine.recipes.${group}`)}
                    className="flex flex-col gap-2"
                  >
                    <h3 className="text-sm font-semibold text-muted">
                      {t(`machine.recipes.${group}`)}
                    </h3>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {members.map((each) => (
                        <button
                          key={each.id}
                          type="button"
                          onClick={() => setRecipe(each)}
                          className="flex flex-col items-start gap-1 rounded border border-line p-3 text-left hover:bg-hover"
                        >
                          <span className="font-medium">{each.title}</span>
                          {each.description && (
                            <span className="text-xs text-muted">{each.description}</span>
                          )}
                          <span className="text-xs text-muted">
                            {each.kind} · {each.memory} · {each.cpus} {t('machine.cpus')} ·{' '}
                            {each.disk}
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>
                );
              })}
              <div className="flex justify-end">
                <Cancel />
              </div>
            </div>
          )}
        </Loaded>
      )}
    </Modal>
  );
}

const NAT = '';

function RecipeForm({
  recipe,
  back,
  onClose,
}: {
  recipe: Recipe;
  back: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const networks = useNetworks();
  const isos = useIsos();
  const inputs = recipe.inputs ?? [];
  const [name, setName] = useState('');
  const [kind, setKind] = useState<GuestClass>(recipe.class);
  const [memory, setMemory] = useState('');
  const [cpus, setCpus] = useState('');
  const [disk, setDisk] = useState('');
  const [network, setNetwork] = useState(NAT);
  const [vlan, setVlan] = useState('');
  const [given, setGiven] = useState<Record<string, string>>({});
  const create = useMachineWrite(
    (api, body: object) => api.send('POST', '/v1/guests', body),
    onClose,
  );
  const valid =
    GUEST_NAME.test(name) &&
    (cpus === '' || /^[1-9]\d*$/.test(cpus)) &&
    (vlan === '' || (/^\d+$/.test(vlan) && Number(vlan) >= 1 && Number(vlan) <= 4094)) &&
    inputs.every((input) => given[input.name]?.trim());

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    create.mutate({
      name,
      recipe: recipe.id,
      ...(kind !== recipe.class && { class: kind }),
      ...(memory.trim() && { memory: memory.trim() }),
      ...(cpus && { cpus: Number(cpus) }),
      ...(disk.trim() && { disk: disk.trim() }),
      ...(inputs.length > 0 && {
        inputs: Object.fromEntries(inputs.map((input) => [input.name, given[input.name].trim()])),
      }),
      ...(network !== NAT && { network }),
      ...(vlan && { vlan: Number(vlan) }),
    });
  };

  const text = (
    label: string,
    value: string,
    set: (value: string) => void,
    placeholder?: string,
  ) => (
    <Labelled label={label}>
      {(id) => (
        <input
          id={id}
          value={value}
          placeholder={placeholder}
          onChange={(event) => set(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          className={field}
        />
      )}
    </Labelled>
  );

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {recipe.description && <p className="text-sm text-muted">{recipe.description}</p>}
      <Labelled label={t('machine.guest.name')}>
        {(id) => (
          <input
            id={id}
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            maxLength={63}
            aria-invalid={name !== '' && !GUEST_NAME.test(name)}
            className={field}
          />
        )}
      </Labelled>
      {name !== '' && !GUEST_NAME.test(name) && (
        <p className="-mt-2 text-xs text-muted">{t('machine.guest.nameRule')}</p>
      )}
      <Picker
        label={t('machine.guest.class')}
        value={kind}
        options={CLASSES.map((each) => [each, t(`machine.class.${each}`)] as const)}
        onChange={setKind}
      />
      <div className="grid grid-cols-3 gap-2">
        {text(t('machine.memory'), memory, setMemory, recipe.memory)}
        {text(t('machine.cpus'), cpus, setCpus, String(recipe.cpus))}
        {text(t('machine.disk'), disk, setDisk, recipe.disk)}
      </div>
      {inputs.map((input) =>
        input.type === 'iso' ? (
          <Labelled key={input.name} label={input.title}>
            {(id) => (
              <select
                id={id}
                value={given[input.name] ?? ''}
                onChange={(event) => setGiven({ ...given, [input.name]: event.target.value })}
                className={field}
              >
                <option value="" disabled>
                  {isos.data?.length ? t('machine.iso.choose') : t('machine.iso.none')}
                </option>
                {isos.data?.map((iso) => (
                  <option key={iso.name} value={iso.name}>
                    {iso.name}
                  </option>
                ))}
              </select>
            )}
          </Labelled>
        ) : (
          <div key={input.name}>
            {text(
              input.title,
              given[input.name] ?? '',
              (value) => setGiven({ ...given, [input.name]: value }),
              '/',
            )}
          </div>
        ),
      )}
      <Failure error={isos.error} />
      <div className="grid grid-cols-[1fr_8rem] gap-2">
        <Labelled label={t('machine.network')}>
          {(id) => (
            <select
              id={id}
              value={network}
              onChange={(event) => setNetwork(event.target.value)}
              className={field}
            >
              <option value={NAT}>{t('machine.network.nat')}</option>
              {networks.data?.map((each) => (
                <option key={each.name} value={each.name}>
                  {each.name} ({each.type})
                </option>
              ))}
            </select>
          )}
        </Labelled>
        {text(t('machine.network.vlan'), vlan, setVlan)}
      </div>
      <Failure error={networks.error} />
      <Failure error={create.error} />
      <div className="flex justify-between gap-2">
        <button type="button" className={button} onClick={back}>
          {t('machine.recipes.back')}
        </button>
        <div className="flex gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={!valid || create.isPending}>
            {t('machine.guest.create')}
          </button>
        </div>
      </div>
    </form>
  );
}

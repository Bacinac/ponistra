import { useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import {
  CLASSES,
  GROUPS,
  GUEST_NAME,
  OWNED,
  useIsos,
  useMachineWrite,
  useNetwork,
  useNetworks,
  useRecipes,
  type GuestClass,
  type Recipe,
  type RecipeInput,
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
                          <Opens recipe={each} />
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

/** What the recipe's firewall lets in from the guest's first start. */
function Opens({ recipe }: { recipe: Recipe }) {
  const { t } = useI18n();
  if (!recipe.open) return null;
  return (
    <span className="text-xs">
      {recipe.open === 'any' ? (
        t('machine.recipe.opensAll')
      ) : (
        <>
          {t('machine.recipe.opens')} <span className="font-mono">{recipe.open}</span>
        </>
      )}
    </span>
  );
}

const fits = (input: RecipeInput, value: string | undefined) => {
  const given = value?.trim() ?? '';
  if (!given) return input.default !== undefined;
  if (!input.pattern) return true;
  try {
    return new RegExp(`^(?:${input.pattern})$`).test(given);
  } catch {
    return true;
  }
};

const RECIPE_NETWORK = '';
const LAN = 'lan';

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
  const ports = inputs.some((input) => input.type === 'port');
  const machineNetwork = useNetwork(ports);
  const owned = recipe.group === OWNED;
  const [owner, setOwner] = useState('');
  const [name, setName] = useState('');
  const [kind, setKind] = useState<GuestClass>(recipe.class);
  const [memory, setMemory] = useState('');
  const [cpus, setCpus] = useState('');
  const [disk, setDisk] = useState('');
  const [network, setNetwork] = useState(RECIPE_NETWORK);
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
    inputs.every((input) => fits(input, given[input.name]));

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
        inputs: Object.fromEntries(
          inputs
            .filter((input) => given[input.name]?.trim())
            .map((input) => [input.name, given[input.name].trim()]),
        ),
      }),
      ...(owned && owner.trim() && { owner: owner.trim() }),
      ...(network !== RECIPE_NETWORK && { network }),
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
      {inputs.map((input) => (
        <InputField
          key={input.name}
          input={input}
          value={given[input.name] ?? ''}
          set={(value) => setGiven({ ...given, [input.name]: value })}
          isos={isos.data?.map((iso) => iso.name) ?? []}
          ports={
            machineNetwork.data
              ? (machineNetwork.data.config.guest_ports ?? []).map((mac) => ({
                  mac,
                  name: machineNetwork.data.links?.find((link) => link.mac === mac)?.name ?? mac,
                }))
              : []
          }
        />
      ))}
      <Failure error={isos.error} />
      {ports && <Failure error={machineNetwork.error} />}
      {owned && (
        <>
          {text(t('machine.guest.owner'), owner, setOwner)}
          <p className="-mt-2 text-xs text-muted">{t('machine.guest.ownerRule')}</p>
        </>
      )}
      <Opens recipe={recipe} />
      <div className="grid grid-cols-[1fr_8rem] gap-2">
        <Labelled label={t('machine.network')}>
          {(id) => (
            <select
              id={id}
              value={network}
              onChange={(event) => setNetwork(event.target.value)}
              className={field}
            >
              <option value={RECIPE_NETWORK}>
                {recipe.network
                  ? `${t('machine.network.recipe')} (${recipe.network})`
                  : t('machine.network.nat')}
              </option>
              <option value={LAN}>{t('machine.network.lan')}</option>
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

function InputField({
  input,
  value,
  set,
  isos,
  ports,
}: {
  input: RecipeInput;
  value: string;
  set: (value: string) => void;
  isos: string[];
  ports: { mac: string; name: string }[];
}) {
  const { t } = useI18n();
  const choices =
    input.type === 'iso'
      ? isos.map((name) => [name, name] as const)
      : input.type === 'port'
        ? ports.map((port) => [port.name, `${port.name} (${port.mac})`] as const)
        : null;
  return (
    <Labelled label={input.title}>
      {(id) =>
        choices ? (
          <select
            id={id}
            value={value}
            onChange={(event) => set(event.target.value)}
            className={field}
          >
            <option value="" disabled={input.default === undefined}>
              {choices.length
                ? t(input.type === 'iso' ? 'machine.iso.choose' : 'machine.port.choose')
                : t(input.type === 'iso' ? 'machine.iso.none' : 'machine.port.none')}
            </option>
            {choices.map(([choice, label]) => (
              <option key={choice} value={choice}>
                {label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            type={input.type === 'secret' ? 'password' : 'text'}
            value={value}
            placeholder={input.type === 'path' ? '/' : input.default}
            onChange={(event) => set(event.target.value)}
            maxLength={1024}
            autoComplete={input.type === 'secret' ? 'new-password' : 'off'}
            spellCheck={false}
            aria-invalid={value !== '' && !fits(input, value)}
            className={field}
          />
        )
      }
    </Labelled>
  );
}

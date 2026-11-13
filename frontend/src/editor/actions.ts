import {
  AlarmClock,
  ArrowDownToLine,
  ArrowUpToLine,
  Ban,
  Bot,
  Briefcase,
  BrushCleaning,
  Calculator,
  ChartNoAxesCombined,
  ChartSpline,
  Check,
  CheckCheck,
  Divide,
  Feather,
  FileDiff,
  FolderInput,
  FolderSymlink,
  Receipt,
  FolderTree,
  GitCompareArrows,
  Hash,
  Hourglass,
  Inbox,
  Languages,
  ListChecks,
  ListCollapse,
  ListTree,
  ListX,
  Mail,
  MailOpen,
  MessageSquareMore,
  Mic,
  Paintbrush,
  PenLine,
  Scissors,
  Search,
  ShieldBan,
  Sigma,
  SpellCheck,
  SquareSigma,
  Star,
  StarOff,
  TableProperties,
  Trash2,
  Undo2,
  X,
  type LucideIcon,
} from 'lucide-react';
import type { EditorState } from 'prosemirror-state';
import type { EditorView } from 'prosemirror-view';
import { ApiError } from '../api';
import { localeName, type Language } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { rangeOf } from './charts';
import {
  ANYWHERE,
  columnOf,
  editing,
  later,
  TABLE,
  TEXT,
  type Context,
  type Dialog,
  type EditorCommand,
  type Group,
  type Where,
} from './command';
import type { Grid } from './grids';
import { hasProposals, proposalsAt } from './proposals';
import { startRun, type Action, type Addressed, type TabTarget } from './runs';
import { targetOf } from './tablesPlugin';
import { reachable } from '../live';

/** How an action shows: its label and icon and, where its target's do not fit, its group and
 * when it can run. */
interface Look {
  label: MessageKey;
  icon: LucideIcon;
  group?: Group;
  when?: (view: EditorView) => boolean;
  /** Of an action its one parameter runs one of several ways: the submenu's group and how each
   * way shows in it, in the interface's language. */
  ways?: { group: Group; look: (value: string, language: Language) => Way | undefined };
  /** Of an action whose parameters the user gives first, the dialog that asks for them and the
   * menu's label that opens it. */
  asks?: { dialog: Dialog; label: MessageKey };
  /** The parameters the interface gives it, in the interface's language. */
  given?: (label: (key: MessageKey) => string) => Parameters;
}

type Way = ({ detail: MessageKey } | { sample: string }) & {
  icon: LucideIcon;
  /** Where the way is offered on the place alone, as a total of numbers on a column of them. */
  when?: (view: EditorView) => boolean;
};

const REWRITE_WAYS: Record<string, Way> = {
  formal: { detail: 'action.textRewrite.formal', icon: Briefcase },
  simple: { detail: 'action.textRewrite.simple', icon: Feather },
  short: { detail: 'action.textRewrite.short', icon: Scissors },
  correct: { detail: 'action.textRewrite.correct', icon: SpellCheck },
};

/** Whether the column the cursor is in holds numbers alone, at least one, in the rows the browser
 * holds below the first, as the server read them: a typed cell without a value is text. What the
 * rows the browser does not hold say, the server checks. */
function numbersIn(view: EditorView): boolean {
  const target = targetOf(view);
  const lines = target?.table.lines;
  return !!target && !!lines && numberColumn(lines, columnOf(view, target));
}

/** Whether the column holds numbers alone below the first row, as the browser holds them. */
export function numberColumn(lines: Grid, col: string): boolean {
  const kinds = [...lines.held.keys()]
    .filter((row) => lines.rowIndex(row) > 0)
    .map((row) => {
      const value = lines.value(row, col);
      if (value) return value.kind;
      const cell = lines.cell(row, col);
      return cell?.text || cell?.formula ? 'text' : undefined;
    });
  return kinds.includes('number') && kinds.every((kind) => kind === undefined || kind === 'number');
}

const TOTAL_WAYS: Record<string, Way> = {
  sum: { detail: 'action.tableTotal.sum', icon: Sigma, when: numbersIn },
  average: { detail: 'action.tableTotal.average', icon: Divide, when: numbersIn },
  count: { detail: 'action.tableTotal.count', icon: Hash, when: numbersIn },
  counta: { detail: 'action.tableTotal.counta', icon: ListChecks },
  min: { detail: 'action.tableTotal.min', icon: ArrowDownToLine, when: numbersIn },
  max: { detail: 'action.tableTotal.max', icon: ArrowUpToLine, when: numbersIn },
  none: { detail: 'action.tableTotal.none', icon: Ban },
};

const ACTION_LOOKS: Record<string, Look> = {
  'table.totals': { label: 'action.tableTotals', icon: SquareSigma },
  'table.total': {
    label: 'action.tableTotal',
    icon: Sigma,
    ways: { group: 'total', look: (value) => TOTAL_WAYS[value] },
  },
  'table.calculate': {
    label: 'action.tableCalculate',
    icon: Calculator,
    asks: { dialog: 'calculate', label: 'action.tableCalculate.ask' },
  },
  'table.clean': { label: 'action.tableClean', icon: BrushCleaning },
  'table.group': { label: 'action.tableGroup', icon: ListTree },
  'table.chart': { label: 'action.tableChart', icon: ChartNoAxesCombined },
  'table.analyse': {
    label: 'action.tableAnalyse',
    icon: ChartSpline,
    given: (label) => ({ title: label('agent.analysis') }),
  },
  'document.tidy': { label: 'action.documentTidy', icon: Paintbrush },
  'search.translate': { label: 'action.searchTranslate', icon: Search },
  'mail.translate': { label: 'action.mailTranslate', icon: Languages },
  'mail.translateReply': { label: 'action.mailTranslateReply', icon: Languages },
  'mail.seen': { label: 'mail.markSeen', icon: MailOpen },
  'mail.unseen': { label: 'mail.markUnseen', icon: Mail },
  'mail.flagged': { label: 'favourites.add', icon: Star },
  'mail.unflagged': { label: 'favourites.remove', icon: StarOff },
  'mail.move': { label: 'mail.moveTo', icon: FolderInput },
  'mail.snooze': { label: 'mail.snooze', icon: AlarmClock },
  'mail.unsnooze': { label: 'mail.unsnooze', icon: Inbox },
  'mail.await': { label: 'mail.await', icon: Hourglass },
  'mail.unawait': { label: 'mail.unawait', icon: Undo2 },
  'mail.delete': { label: 'mail.deleteForGood', icon: Trash2 },
  'mail.block': { label: 'mail.blockTitle', icon: ShieldBan },
  'mail.always': { label: 'mail.alwaysTitle', icon: FolderSymlink },
  'mail.gather': { label: 'collections.addTitle', icon: Receipt },
  'mail.triage': { label: 'action.mailTriage', icon: FolderTree },
  'file.translate': { label: 'action.fileTranslate', icon: Languages },
  'speech.understand': { label: 'action.speechUnderstand', icon: Mic },
  'vault.sort': { label: 'action.vaultSort', icon: FolderTree },
  'text.summarise': { label: 'action.textSummarise', icon: ListCollapse },
  'text.rewrite': {
    label: 'action.textRewrite',
    icon: PenLine,
    ways: { group: 'rewrite', look: (value) => REWRITE_WAYS[value] },
  },
  'text.extract': { label: 'action.textExtract', icon: TableProperties },
  'nodes.extract': { label: 'action.nodesExtract', icon: TableProperties },
  'agent.edit': { label: 'action.agentEdit', icon: Bot },
  'document.compare': {
    label: 'action.documentCompare',
    icon: GitCompareArrows,
    group: 'writing',
    asks: { dialog: 'compare', label: 'action.documentCompare.ask' },
  },
  'file.compare': {
    label: 'action.fileCompare',
    icon: FileDiff,
    group: 'writing',
    asks: { dialog: 'compareFile', label: 'action.fileCompare.ask' },
  },
  'document.translate': {
    label: 'action.documentTranslate',
    icon: Languages,
    group: 'writing',
    ways: {
      group: 'translate',
      look: (value, language) => ({ sample: localeName(value, language), icon: Languages }),
    },
  },
  'text.ask': {
    label: 'action.textAsk',
    icon: MessageSquareMore,
    asks: { dialog: 'ask', label: 'action.textAsk.ask' },
  },
  'proposal.accept': { label: 'action.proposalAccept', icon: Check },
  'proposal.reject': { label: 'action.proposalReject', icon: X },
  'document.accept': {
    label: 'action.documentAccept',
    icon: CheckCheck,
    group: 'review',
    when: (view) => hasProposals(view.state),
  },
  'document.reject': {
    label: 'action.documentReject',
    icon: ListX,
    group: 'review',
    when: (view) => hasProposals(view.state),
  },
};

/** Where each kind of action applies, from the cursor: null where it cannot. */
const TARGETS: Record<
  TabTarget,
  { group: Group; where: readonly Where[]; of: (view: EditorView) => Addressed | null }
> = {
  table: {
    group: 'tableData',
    where: TABLE,
    of: (view) => {
      const target = targetOf(view);
      return target && { table: target.table.node.attrs.id };
    },
  },
  column: {
    group: 'tableData',
    where: TABLE,
    of: (view) => {
      const target = targetOf(view);
      return target && { table: target.table.node.attrs.id, col: columnOf(view, target) };
    },
  },
  range: {
    group: 'tableData',
    where: TABLE,
    of: (view) => {
      const target = targetOf(view);
      if (!target) return null;
      const { table, rect, range } = target;
      const id = table.node.attrs.id;
      return range && table.lines ? { ...rangeOf(id, table.lines, rect) } : { table: id };
    },
  },
  document: { group: 'document', where: ANYWHERE, of: () => ({}) },
  text: { group: 'writing', where: TEXT, of: (view) => blocksOf(view.state) },
  proposals: {
    group: 'review',
    where: ANYWHERE,
    of: (view) => {
      const ids = proposalsAt(view.state).map((proposal) => proposal.id);
      return ids.length ? { ids } : null;
    },
  },
};

/** The blocks of the text the selection reaches, none for the whole tab where nothing is
 * selected. */
function blocksOf(state: EditorState): Addressed {
  const { from, to, empty } = state.selection;
  if (empty) return {};
  const ids: string[] = [];
  state.doc.forEach((node, at) => {
    if (at < to && at + node.nodeSize > from && node.attrs.id) ids.push(node.attrs.id as string);
  });
  return ids.length ? { blocks: ids } : {};
}

export function actionLabel(id: string): MessageKey {
  const look = ACTION_LOOKS[id];
  if (!look) throw new Error(`The action ${id} has no label`);
  return look.label;
}

interface Choosing {
  properties?: Record<string, { enum?: readonly string[] }>;
  required?: readonly string[];
}

/** The parameter that picks the way an action runs, and its values, where it has one. */
function wayOf(action: Action): [string, readonly string[]] | null {
  const { properties = {}, required = [] } = action.parameters as Choosing;
  const [name] = required;
  const values = name === undefined ? undefined : properties[name]?.enum;
  return values ? [name, values] : null;
}

/** An action of the backend, run on the document, the table the cursor is in, its column, the
 * selected cells or the selected text; one that needs a model is disabled while the
 * installation's AI is off. One whose dialog asks for its parameters opens it; else one run one
 * of several ways opens a submenu of them. */
function actionCommands(
  action: Action & { target: TabTarget },
  ai: boolean,
  language: Language,
): EditorCommand[] {
  const { group, where, of } = TARGETS[action.target];
  const look = ACTION_LOOKS[action.id];
  const off = action.model !== null && !ai;
  const command = (
    parameters: Record<string, string>,
    when?: (view: EditorView) => boolean,
  ): EditorCommand => ({
    id: `action.${action.id}`,
    label: actionLabel(action.id),
    icon: look.icon,
    group: look.group ?? group,
    where,
    why: off ? 'ai.off' : undefined,
    enabled: editing(
      ({ view, place }) =>
        !off &&
        reachable() &&
        place.tab !== null &&
        of(view) !== null &&
        (look.when?.(view) ?? true) &&
        (when?.(view) ?? true),
    ),
    run: (context) => {
      const target = of(context.view);
      if (target) {
        runAction(context, action.id, target, { ...parameters, ...look.given?.(context.label) });
      }
    },
  });
  if (look.asks) {
    const { dialog, label } = look.asks;
    return [{ ...command({}), label, run: (context) => context.open(dialog) }];
  }
  const way = wayOf(action);
  if (!way) return [command({})];
  const [name, values] = way;
  if (!look.ways) throw new Error(`The action ${action.id} has no look for its ways`);
  const { group: sub, look: lookOf } = look.ways;
  return [
    { ...command({}), sub, run: () => {} },
    ...values.map((value): EditorCommand => {
      const found = lookOf(value, language);
      if (!found) throw new Error(`The action ${action.id} has no look for ${value}`);
      const { when, ...shown } = found;
      return {
        ...command({ [name]: value }, when),
        ...shown,
        id: `action.${action.id}.${value}`,
        group: sub,
      };
    }),
  ];
}

/** What an action is given beside its target. */
export type Parameters = Record<string, string | string[]>;

/** Runs the action on the target in the tab, offering to take the run back once done; a
 * model's action the document has not been let send out asks the user first. */
export function runAction(
  context: Context,
  action: string,
  target: Addressed,
  parameters: Parameters = {},
): void {
  const { tab } = context.place;
  if (!tab) return;
  const start = (once?: 'once'): Promise<void> =>
    startRun(tab, action, target, parameters, once).then(context.ran, (error: unknown) => {
      if (!(error instanceof ApiError && error.code === 'consent_needed')) throw error;
      context.consent((given) => later(context, start(given === 'once' ? given : undefined)));
    });
  later(context, start());
}

/** Runs an action whose parameters its dialog asked for, on the target the cursor gives it once
 * they are given. */
export function runAsked(context: Context, action: string, parameters: Parameters): void {
  const found = backendActions.find((each) => each.id === action);
  if (!found) throw new Error(`The action ${action} is not offered`);
  const target = TARGETS[found.target].of(context.view);
  if (target) runAction(context, action, target, parameters);
}

let backendActions: readonly (Action & { target: TabTarget })[] = [];
let offered: readonly EditorCommand[] = [];

/** Puts the backend's actions on a part of a tab among the commands, each in the group of its
 * target's, those that need a model enabled only where the installation's AI is on. */
export function offerActions(actions: readonly Action[], ai: boolean, language: Language): void {
  backendActions = actions.filter((action): action is Action & { target: TabTarget } =>
    Object.hasOwn(TARGETS, action.target),
  );
  offered = backendActions.flatMap((action) => actionCommands(action, ai, language));
}

/** The command of a backend's action, once the actions have arrived. */
export function offeredAction(id: string): EditorCommand | undefined {
  return offered.find((command) => command.id === `action.${id}`);
}

export function offeredCommands(): readonly EditorCommand[] {
  return offered;
}

import type { MessageKey } from '../i18n/hr';
import type { Condition, ConditionOp } from './grids';

export const CONDITION_LABELS: Record<ConditionOp, MessageKey> = {
  equals: 'filter.equals',
  notEquals: 'filter.notEquals',
  begins: 'filter.begins',
  ends: 'filter.ends',
  contains: 'filter.contains',
  notContains: 'filter.notContains',
  greater: 'filter.greater',
  greaterEqual: 'filter.greaterEqual',
  less: 'filter.less',
  lessEqual: 'filter.lessEqual',
};

/** What a condition keeps, as its chip reads. */
export function conditionText(condition: Condition, label: (key: MessageKey) => string): string {
  if ('values' in condition) {
    const shown = condition.values.slice(0, 3).map((value) => value || label('filter.empty'));
    return shown.join(', ') + (condition.values.length > 3 ? ', …' : '');
  }
  return `${label(CONDITION_LABELS[condition.op])} ${condition.value}`;
}

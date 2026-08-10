export { ContextsHeader } from './ContextsHeader';
export { ContextsLoading } from './ContextsLoading';
export { ContextsEmpty } from './ContextsEmpty';
export { ContextRow } from './ContextRow';
export { LiveSituationRow } from './LiveSituationRow';
export { CurrentPeriodSection } from './CurrentPeriodSection';
export { LifeAreasSection } from './LifeAreasSection';
export {
  buildContextsMap,
  buildLifeAreas,
  buildLiveSituations,
  type ContextsMapModel,
  type LifeAreaRow,
  type LiveSituationRow as LiveSituationModel,
} from './buildContextsMap';
export { domainLabel, DOMAIN_LABELS_IT } from './buildContextsMap';
export { mapFromLifeMapApi } from './mapFromLifeMapApi';

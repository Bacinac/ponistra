import { lazy, Suspense } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { idIn } from './address';
import { Loading } from './frame';
import { useSaved } from './saved';
import { Failure } from './tree';

const Presenter = lazy(() => import('./editor/Presenter'));

/** The presenter's window of a show running in another window of the same browser, which names
 * it by `show`. */
export function PresentPage() {
  const nodeId = idIn(useParams().node) ?? '';
  const show = useSearchParams()[0].get('show') ?? '';
  const { placement, own, states, grids, error } = useSaved(nodeId, `presenter:${show}`);
  if (error) return <Failure error={error} />;
  if (!placement || !own || !states || !grids) return <Loading />;
  return (
    <Suspense fallback={<Loading />}>
      <Presenter
        show={show}
        title={placement.node.title}
        own={own}
        tabs={placement.tabs}
        states={states}
        grids={grids}
        locale={placement.node.locale}
      />
    </Suspense>
  );
}

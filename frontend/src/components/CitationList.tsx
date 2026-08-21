import type { HrCitation } from "../api/hrRag";

interface CitationListProps {
  citations: HrCitation[];
}

/**
 * The approved HR sources an answer referenced, collapsed behind a control.
 *
 * `details`/`summary` is used rather than a custom disclosure widget: it gives
 * keyboard operation, focus, and the expanded/collapsed state to assistive
 * technology natively, with no ARIA to keep in sync. The citations stay in the
 * DOM while collapsed, so nothing is re-fetched or re-rendered on toggle.
 *
 * Neither `distance` nor `citation_id` is shown: both are internal mapping
 * detail rather than something a reader can act on. `citation_id` remains the
 * React key and stays in the data model, so the attribution the grounding
 * service validated is intact.
 */
export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <details className="citations">
      <summary className="citations__summary">
        Sources
        <span className="citations__count">{citations.length}</span>
      </summary>
      <ol className="citations__list">
        {citations.map((citation) => (
          <li className="citation" key={citation.citation_id}>
            <div className="citation__body">
              <p className="citation__title">{citation.document_title}</p>
              <p className="citation__heading-path">{citation.heading_path}</p>
              <p className="citation__key">{citation.document_key}</p>
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}

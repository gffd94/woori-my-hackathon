import { safeSourceHref } from '../api/resultDetails.js';

const SOURCE_NAMES = { boho_security_notice: '보호나라' };

// 주요 위험 신호 바로 아래에 실제 연결된 출처만 간단히 표시합니다.
export function EvidenceDetails({ evidence = [] }) {
  const seen = new Set();
  const sources = evidence.flatMap((item) => item.sources || []).filter((source) => {
    const key = JSON.stringify([source.site, source.url, source.title]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (!sources.length) return null;
  return (
    <ul className="evidence__sources" aria-label="참고 출처">
      {sources.map((source, index) => {
        const href = safeSourceHref(source.url);
        const site = SOURCE_NAMES[source.site] || source.site || source.title || '출처 미등록';
        return (
          <li key={index}>
            <span>{`출처 : ${site}`}</span>
            {href && <> (<a href={href} target="_blank" rel="noopener noreferrer"
              aria-label={`${source.title || site} 원문보기 (새 탭)`}>원문보기</a>)</>}
          </li>
        );
      })}
    </ul>
  );
}

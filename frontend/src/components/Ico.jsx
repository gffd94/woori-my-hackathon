import { fig } from '../assets.js';

/**
 * Figma 아이콘 한 개. w·h는 Figma 레이어 크기, inset은 선 두께만큼 바깥으로 넓힌 영역(Figma 코드 그대로).
 */
export default function Ico({ name, w, h, inset, className = '', style }) {
  return (
    <span className={`ico ${className}`} style={{ width: w, height: h, ...style }} aria-hidden="true">
      <span className="ico__in" style={inset ? { inset } : undefined}>
        <img src={fig(name)} alt="" draggable="false" />
      </span>
    </span>
  );
}

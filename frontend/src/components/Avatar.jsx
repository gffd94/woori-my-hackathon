import Ico from './Ico.jsx';
import { fig } from '../assets.js';

// 위비 아바타. size 38 = 첫 안내(7:2527), 34 = 분석 중(7:2561)
export default function Avatar({ size = 38 }) {
  const small = size === 34;
  return (
    <span className="avatar" style={{ width: size, height: size }} aria-hidden="true">
      <Ico name={small ? 'avatar-circle-sm.svg' : 'avatar-circle.svg'} w={size} h={size} />
      <img className="avatar__img" src={fig('wibee.png')} alt=""
        style={small ? { left: 7, top: 4, width: 20, height: 25 } : { left: 7, top: 4, width: 24, height: 30 }} />
    </span>
  );
}

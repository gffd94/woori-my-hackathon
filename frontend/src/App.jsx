import { useState, useRef } from 'react';
import HomeScreen from './screens/HomeScreen.jsx';
import ChatScreen from './screens/ChatScreen.jsx';
import Toast from './components/Toast.jsx';
import { readSharedText, readSampleKey } from './bridge.js';

export default function App() {
  const shared = readSharedText();
  const [screen, setScreen] = useState(shared || readSampleKey() ? 'chat' : 'home');
  const [toast, setToast] = useState('');
  const timer = useRef(null);
  const showToast = (m) => {
    setToast(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(''), 2200);
  };

  return (
    <div className="device">
      {screen === 'home'
        ? <><HomeScreen onOpenSafeTalk={() => setScreen('chat')} onToast={showToast} /><Toast message={toast} /></>
        : <ChatScreen onExit={() => setScreen('home')} sharedText={shared} />}
    </div>
  );
}

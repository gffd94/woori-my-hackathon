export default function Toast({ message }) {
  return <div className={`toast${message ? ' toast--on' : ''}`} role="status" aria-live="polite">{message}</div>;
}

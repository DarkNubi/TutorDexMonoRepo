import { AlertCircle } from 'lucide-react';
import './DuplicateBadge.css';

export function DuplicateBadge({ count, onClick }) {
  if (!count || count < 2) return null;
  
  const otherCount = count - 1;
  
  return (
    <div className="duplicate-badge" onClick={onClick}>
      <AlertCircle size={16} className="duplicate-badge-icon" />
      <span className="duplicate-badge-text">
        Also posted by {otherCount} other {otherCount === 1 ? 'agency' : 'agencies'}
      </span>
      <button 
        type="button"
        className="duplicate-badge-button"
        onClick={(e) => {
          e.stopPropagation();
          onClick && onClick();
        }}
      >
        View All
      </button>
    </div>
  );
}

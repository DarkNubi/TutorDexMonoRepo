import { useState, useEffect } from 'react';
import { X, ExternalLink, Star } from 'lucide-react';
import { fetchAssignmentDuplicates } from '../../backend.js';
import './DuplicateModal.css';

export function DuplicateModal({ assignmentId, isOpen, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  useEffect(() => {
    if (isOpen && assignmentId) {
      fetchDuplicates();
    }
  }, [isOpen, assignmentId]);
  
  const fetchDuplicates = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAssignmentDuplicates(assignmentId);
      setData(result);
    } catch (err) {
      setError(err.message || 'Failed to load duplicates');
    } finally {
      setLoading(false);
    }
  };
  
  if (!isOpen) return null;
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">Duplicate Assignments</h2>
            {data && (
              <p className="modal-subtitle">
                {data.duplicates?.length || 0} versions found
              </p>
            )}
          </div>
          <button 
            type="button"
            className="modal-close" 
            onClick={onClose}
            aria-label="Close"
          >
            <X size={24} />
          </button>
        </div>
        
        <div className="modal-body">
          {loading && (
            <div className="modal-loading">
              <div className="spinner"></div>
              <p>Loading duplicates...</p>
            </div>
          )}
          
          {error && (
            <div className="modal-error">
              <p>Error: {error}</p>
              <button 
                type="button"
                onClick={fetchDuplicates}
                className="retry-button"
              >
                Retry
              </button>
            </div>
          )}
          
          {data && !loading && (
            <div className="duplicates-grid">
              {data.duplicates?.map(assignment => (
                <div 
                  key={assignment.id} 
                  className={`duplicate-card ${assignment.is_primary_in_group ? 'primary' : ''}`}
                >
                  {assignment.is_primary_in_group && (
                    <div className="primary-badge">
                      <Star size={14} fill="currentColor" />
                      Primary
                    </div>
                  )}
                  
                  <h3 className="duplicate-agency">{assignment.agency_name}</h3>
                  
                  <div className="duplicate-details">
                    <div className="duplicate-row">
                      <span className="label">Assignment Code:</span>
                      <span className="value">{assignment.assignment_code || 'N/A'}</span>
                    </div>
                    
                    <div className="duplicate-row">
                      <span className="label">Posted:</span>
                      <span className="value">
                        {new Date(assignment.published_at).toLocaleDateString()}
                      </span>
                    </div>
                    
                    {assignment.duplicate_confidence_score != null && (
                      <div className="duplicate-row">
                        <span className="label">Match Score:</span>
                        <span className="value confidence">
                          {assignment.duplicate_confidence_score.toFixed(1)}%
                        </span>
                      </div>
                    )}
                    
                    {assignment.message_link && (
                      <a 
                        href={assignment.message_link} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="duplicate-link"
                      >
                        View Original <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

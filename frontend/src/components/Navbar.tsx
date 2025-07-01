import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Video, List } from 'lucide-react';

const Navbar = ({ onBoardSelect, currentView }: { onBoardSelect: (cb: number | null) => void, currentView: string }) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const communityBoards = [
    { number: 1, name: 'CB 1' },
    { number: 2, name: 'CB 2' },
    { number: 3, name: 'CB 3' },
    { number: 4, name: 'CB 4' },
    { number: 5, name: 'CB 5' },
    { number: 6, name: 'CB 6' },
    { number: 7, name: 'CB 7' },
    { number: 8, name: 'CB 8' },
    { number: 9, name: 'CB 9' },
    { number: 10, name: 'CB 10' },
    { number: 11, name: 'CB 11' },
    { number: 12, name: 'CB 12' },
  ];

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <header className="navbar">
      <div className="navbar-content">
        <a href="#" onClick={() => onBoardSelect(null)} className="navbar-brand">
          <img src="/logo.png" alt="CB Analyzer Logo" className="navbar-logo" />
          <span>CB Analyzer</span>
        </a>

        <div className="navbar-nav">
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              onBoardSelect(null);
            }}
            className={`navbar-link ${currentView === 'analyzer' ? 'active' : ''}`}
          >
            <Video size={16} />
            <span>Analyze Video</span>
          </a>
          <div className="navbar-dropdown" ref={dropdownRef}>
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className={`navbar-link ${currentView === 'meetings' ? 'active' : ''}`}
            >
              <List size={16} />
              <span>CB Meetings</span>
              <ChevronDown size={16} className={`dropdown-chevron ${isDropdownOpen ? 'open' : ''}`} />
            </button>
            {isDropdownOpen && (
              <div className="dropdown-menu">
                <div className="dropdown-grid">
                  {communityBoards.map((cb) => (
                    <a
                      key={cb.number}
                      href="#"
                      className="dropdown-item"
                      onClick={(e) => {
                        e.preventDefault();
                        onBoardSelect(cb.number);
                        setIsDropdownOpen(false);
                      }}
                    >
                      {cb.name}
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default Navbar;

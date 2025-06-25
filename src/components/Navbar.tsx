import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Menu, X } from 'lucide-react';

interface NavbarProps {
  onBoardSelect: (boardNumber: number | null) => void;
  currentView: 'analyzer' | 'meetings';
}

interface Board {
  number: number;
  name: string;
  district: string;
}

const Navbar: React.FC<NavbarProps> = ({ onBoardSelect, currentView }) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const boards: Board[] = [
    { number: 1, name: 'Manhattan CB1', district: 'Financial District' },
    { number: 2, name: 'Manhattan CB2', district: 'Greenwich Village' },
    { number: 3, name: 'Manhattan CB3', district: 'Lower East Side' },
    { number: 4, name: 'Manhattan CB4', district: 'Chelsea/Clinton' },
    { number: 5, name: 'Manhattan CB5', district: 'Midtown' },
    { number: 6, name: 'Manhattan CB6', district: 'East Midtown' },
    { number: 7, name: 'Manhattan CB7', district: 'Upper West Side' },
    { number: 8, name: 'Manhattan CB8', district: 'Upper East Side' },
    { number: 9, name: 'Manhattan CB9', district: 'West Harlem' },
    { number: 10, name: 'Manhattan CB10', district: 'Central Harlem' },
    { number: 11, name: 'Manhattan CB11', district: 'East Harlem' },
    { number: 12, name: 'Manhattan CB12', district: 'Washington Heights' },
  ];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleBoardClick = (boardNumber: number) => {
    onBoardSelect(boardNumber);
    setIsDropdownOpen(false);
    setIsMobileMenuOpen(false);
  };

  const navStyles = {
    nav: {
      background: 'white',
      boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
      position: 'sticky' as const,
      top: 0,
      zIndex: 1000,
      borderBottom: '1px solid #e2e8f0'
    },
    container: {
      maxWidth: '1200px',
      maWidth: '900px',
      margin: '0 auto',
      padding: '0 1rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      height: '64px'
    },
    logo: {
      display: 'flex',
      alignItems: 'center',
      gap: '0.75rem',
      cursor: 'pointer',
      padding: '0.5rem',
      borderRadius: '0.5rem',
      transition: 'background 0.2s'
    },
    brandText: {
      fontSize: '1.25rem',
      fontWeight: '600',
      color: '#1a202c'
    },
    desktopNav: {
      display: 'flex',
      alignItems: 'center',
      gap: '2rem'
    },
    navButton: {
      background: 'none',
      border: 'none',
      fontWeight: '500',
      cursor: 'pointer',
      padding: '0.5rem 1rem',
      borderRadius: '0.5rem',
      transition: 'all 0.2s'
    },
    dropdown: {
      position: 'absolute' as const,
      top: '100%',
      right: 0,
      marginTop: '0.5rem',
      background: 'white',
      borderRadius: '0.75rem',
      boxShadow: '0 10px 25px rgba(0, 0, 0, 0.1)',
      border: '1px solid #e2e8f0',
      minWidth: '280px',
      maxHeight: '400px',
      overflowY: 'auto' as const,
      animation: 'slideDown 0.2s ease-out'
    },
    mobileMenu: {
      position: 'fixed' as const,
      top: '64px',
      left: 0,
      right: 0,
      bottom: 0,
      background: 'white',
      borderTop: '1px solid #e2e8f0',
      overflowY: 'auto' as const,
      animation: 'slideDown 0.3s ease-out'
    }
  };

  return (
    <>
      <nav style={navStyles.nav}>
        <div style={navStyles.container}>
          {/* Logo/Brand */}
          <div 
            onClick={() => onBoardSelect(null)}
            style={navStyles.logo}
            onMouseEnter={(e) => e.currentTarget.style.background = '#f7fafc'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            <img src='/logo.png' width={32} height={32} alt="CB Analyzer" />
            <span style={navStyles.brandText}>
              CB Analyzer
            </span>
          </div>

          {/* Desktop Navigation */}
          <div style={navStyles.desktopNav} className="desktop-nav">
            <button
              onClick={() => onBoardSelect(null)}
              style={{
                ...navStyles.navButton,
                color: currentView === 'analyzer' ? '#3182ce' : '#4a5568',
                fontWeight: currentView === 'analyzer' ? '600' : '500'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#f7fafc'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              Analyze Video
            </button>

            <div ref={dropdownRef} style={{ position: 'relative' }}>
              <button
                onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                style={{
                  ...navStyles.navButton,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  background: isDropdownOpen ? '#f7fafc' : 'none',
                  color: currentView === 'meetings' ? '#3182ce' : '#4a5568',
                  fontWeight: currentView === 'meetings' ? '600' : '500'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#f7fafc'}
                onMouseLeave={(e) => !isDropdownOpen && (e.currentTarget.style.background = 'transparent')}
              >
                CB Meetings
                <ChevronDown 
                  size={16} 
                  style={{
                    transform: isDropdownOpen ? 'rotate(180deg)' : 'rotate(0)',
                    transition: 'transform 0.2s'
                  }}
                />
              </button>

              {/* Dropdown Menu */}
              {isDropdownOpen && (
                <div style={navStyles.dropdown}>
                  <div style={{ padding: '0.5rem' }}>
                    {boards.map((board) => (
                      <button
                        key={board.number}
                        onClick={() => handleBoardClick(board.number)}
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'flex-start',
                          width: '100%',
                          padding: '0.75rem 1rem',
                          background: 'none',
                          border: 'none',
                          borderRadius: '0.5rem',
                          cursor: 'pointer',
                          transition: 'background 0.2s',
                          textAlign: 'left'
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = '#f7fafc'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                      >
                        <span style={{
                          fontWeight: '600',
                          color: '#1a202c',
                          marginBottom: '0.25rem'
                        }}>
                          {board.name}
                        </span>
                        <span style={{
                          fontSize: '0.875rem',
                          color: '#718096'
                        }}>
                          {board.district}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            style={{
              display: 'none',
              background: 'none',
              border: 'none',
              color: '#4a5568',
              cursor: 'pointer',
              padding: '0.5rem'
            }}
            className="mobile-menu-btn"
          >
            {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Mobile Menu */}
        {isMobileMenuOpen && (
          <div style={navStyles.mobileMenu}>
            <div style={{ padding: '1rem' }}>
              <button
                onClick={() => {
                  onBoardSelect(null);
                  setIsMobileMenuOpen(false);
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  padding: '1rem',
                  background: currentView === 'analyzer' ? '#ebf8ff' : 'none',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: currentView === 'analyzer' ? '#3182ce' : '#4a5568',
                  fontWeight: '600',
                  cursor: 'pointer',
                  marginBottom: '1rem'
                }}
              >
                Analyze Video
              </button>

              <div style={{
                borderTop: '1px solid #e2e8f0',
                paddingTop: '1rem',
                marginBottom: '0.5rem'
              }}>
                <h3 style={{
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  color: '#718096',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: '0.75rem'
                }}>
                  Community Boards
                </h3>
              </div>

              {boards.map((board) => (
                <button
                  key={board.number}
                  onClick={() => handleBoardClick(board.number)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'none',
                    border: 'none',
                    borderRadius: '0.5rem',
                    cursor: 'pointer',
                    transition: 'background 0.2s',
                    textAlign: 'left',
                    marginBottom: '0.5rem'
                  }}
                >
                  <span style={{
                    fontWeight: '600',
                    color: '#1a202c',
                    marginBottom: '0.25rem'
                  }}>
                    {board.name}
                  </span>
                  <span style={{
                    fontSize: '0.875rem',
                    color: '#718096'
                  }}>
                    {board.district}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </nav>

      <style>{`
        @keyframes slideDown {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @media (max-width: 768px) {
          .desktop-nav {
            display: none !important;
          }
          .mobile-menu-btn {
            display: block !important;
          }
        }
      `}</style>
    </>
  );
};

export default Navbar;
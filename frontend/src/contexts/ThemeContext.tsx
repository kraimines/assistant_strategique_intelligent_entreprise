import { createContext, useContext, useEffect } from 'react';

/* ── Light-only design system — theme switching removed ──────────────────── */

interface ThemeContextValue {
  theme: 'light';
  toggleTheme: () => void;  // no-op — kept for API compatibility
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  /* Always enforce light mode on <html> — removes any stale data-theme attr */
  useEffect(() => {
    document.documentElement.removeAttribute('data-theme');
    localStorage.removeItem('theme');
  }, []);

  return (
    <ThemeContext.Provider value={{ theme: 'light', toggleTheme: () => {} }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);

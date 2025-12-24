import { useState, useEffect } from 'react';

const THEMES = [
  'light', 'dark', 'cupcake', 'bumblebee', 'emerald', 'corporate',
  'synthwave', 'retro', 'cyberpunk', 'valentine', 'halloween', 'garden',
  'forest', 'aqua', 'lofi', 'pastel', 'fantasy', 'wireframe', 'black',
  'luxury', 'dracula', 'cmyk', 'autumn', 'business', 'acid', 'lemonade',
  'night', 'coffee', 'winter', 'dim', 'nord', 'sunset'
];

export default function ThemeTab() {
  const [currentTheme, setCurrentTheme] = useState('light');

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') || 'light';
    setCurrentTheme(savedTheme);
    document.documentElement.setAttribute('data-theme', savedTheme);
  }, []);

  const handleThemeChange = (theme: string) => {
    setCurrentTheme(theme);
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
        {THEMES.map((theme) => (
          <button
            key={theme}
            onClick={() => handleThemeChange(theme)}
            className={`flex flex-col items-center p-3 rounded-lg transition-all duration-200 cursor-pointer hover:scale-105 ${
              currentTheme === theme
                ? 'ring-2 ring-primary ring-offset-2 ring-offset-base-100'
                : 'hover:bg-base-200'
            }`}
          >
            <div
              data-theme={theme}
              className="w-full aspect-square rounded-md overflow-hidden bg-base-100 border border-base-300"
            >
              <div className="grid grid-cols-2 grid-rows-2 h-full">
                <div className="bg-primary" />
                <div className="bg-secondary" />
                <div className="bg-accent" />
                <div className="bg-neutral" />
              </div>
            </div>
            <span className="text-xs mt-2 text-base-content/70 capitalize">
              {theme}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

import { useState, useEffect, useRef } from 'react';

/**
 * Hook to control visibility based on scroll behavior.
 * - Hides when scrolling down
 * - Shows when scrolling up or at top of page
 * - Shows after idle timeout (default 2 seconds)
 */
export function useScrollVisibility(idleTimeoutMs = 2000) {
  const [isVisible, setIsVisible] = useState(true);
  const lastScrollY = useRef(0);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      const isScrollingUp = currentScrollY < lastScrollY.current;

      // Clear existing idle timer
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
      }

      // Show if scrolling up or at top
      if (isScrollingUp || currentScrollY < 10) {
        setIsVisible(true);
      } else {
        // Hide when scrolling down
        setIsVisible(false);
      }

      // Set idle timer to show after timeout
      idleTimerRef.current = setTimeout(() => {
        setIsVisible(true);
      }, idleTimeoutMs);

      lastScrollY.current = currentScrollY;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    };
  }, [idleTimeoutMs]);

  return isVisible;
}

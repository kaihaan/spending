import { Outlet } from 'react-router-dom';

/**
 * MainLayout - Simple wrapper for pages that use the FilterDrawer.
 * FilterBar and CategoryDrawer are now rendered at the App level via FilterDrawer.
 */
export default function MainLayout() {
  return <Outlet />;
}

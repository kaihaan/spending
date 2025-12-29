/**
 * Profile Page
 *
 * View and update user profile (username and password).
 * Requires current password for security when changing password.
 */

import { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import * as authApi from '../api/auth';

export default function Profile() {
  const navigate = useNavigate();
  const { user, refreshUser, logout } = useAuth();

  const [username, setUsername] = useState(user?.username || '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Check if anything changed
    const usernameChanged = username !== user?.username;
    const passwordChanging = newPassword.length > 0;

    if (!usernameChanged && !passwordChanging) {
      setError('No changes to save');
      return;
    }

    // Validate password change
    if (passwordChanging) {
      if (!currentPassword) {
        setError('Current password is required to change password');
        return;
      }

      if (newPassword.length < 8) {
        setError('New password must be at least 8 characters');
        return;
      }

      if (newPassword !== confirmPassword) {
        setError('New passwords do not match');
        return;
      }
    }

    try {
      setIsSubmitting(true);

      const updateData: authApi.UpdateProfileRequest = {};

      if (usernameChanged) {
        updateData.username = username.trim();
      }

      if (passwordChanging) {
        updateData.current_password = currentPassword;
        updateData.new_password = newPassword;
      }

      const response = await authApi.updateProfile(updateData);

      if (response.success) {
        setSuccess(response.message || 'Profile updated successfully');

        // Refresh user data
        await refreshUser();

        // Clear password fields
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');

        // If username changed, update local state
        if (response.user) {
          setUsername(response.user.username);
        }
      } else {
        setError(response.error || 'Failed to update profile');
      }
    } catch (err) {
      const errorMessage = authApi.getErrorMessage(err);
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      console.error('Logout failed:', err);
    }
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="loading loading-spinner loading-lg"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-base-200 p-4">
      <div className="container mx-auto max-w-2xl py-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-4xl font-bold">Profile Settings</h1>
          <p className="text-base-content/70 mt-2">Manage your account information</p>
        </div>

        {/* Profile Card */}
        <div className="card bg-base-100 shadow-xl mb-6">
          <div className="card-body">
            {/* Success Alert */}
            {success && (
              <div className="alert alert-success mb-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>{success}</span>
              </div>
            )}

            {/* Error Alert */}
            {error && (
              <div className="alert alert-error mb-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Account Information Section */}
              <div>
                <h3 className="text-lg font-semibold mb-4">Account Information</h3>

                {/* Email (Read-only) */}
                <div className="form-control mb-4">
                  <label className="label">
                    <span className="label-text">Email</span>
                    <span className="label-text-alt">Read-only</span>
                  </label>
                  <input
                    type="email"
                    value={user.email}
                    className="input input-bordered w-full"
                    disabled
                  />
                </div>

                {/* Username */}
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Username</span>
                  </label>
                  <input
                    type="text"
                    placeholder="Enter your username"
                    className="input input-bordered w-full"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>
              </div>

              <div className="divider"></div>

              {/* Change Password Section */}
              <div>
                <h3 className="text-lg font-semibold mb-4">Change Password</h3>

                {/* Current Password */}
                <div className="form-control mb-4">
                  <label className="label">
                    <span className="label-text">Current Password</span>
                  </label>
                  <input
                    type="password"
                    placeholder="Enter current password"
                    className="input input-bordered w-full"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>

                {/* New Password */}
                <div className="form-control mb-4">
                  <label className="label">
                    <span className="label-text">New Password</span>
                    <span className="label-text-alt">Min 8 characters</span>
                  </label>
                  <input
                    type="password"
                    placeholder="Enter new password"
                    className="input input-bordered w-full"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>

                {/* Confirm New Password */}
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Confirm New Password</span>
                  </label>
                  <input
                    type="password"
                    placeholder="Re-enter new password"
                    className="input input-bordered w-full"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>
              </div>

              {/* Submit Button */}
              <div className="card-actions justify-end mt-6">
                <button
                  type="submit"
                  className={`btn btn-primary ${isSubmitting ? 'loading' : ''}`}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Logout Section */}
        <div className="card bg-base-100 shadow-xl">
          <div className="card-body">
            <h3 className="text-lg font-semibold mb-2">Sign Out</h3>
            <p className="text-base-content/70 mb-4">
              End your current session and return to the login page
            </p>
            <div className="card-actions">
              <button onClick={handleLogout} className="btn btn-outline btn-error">
                Logout
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

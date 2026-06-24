import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

export default function Login() {
  const navigate = useNavigate();
  const { login, register, isAuthenticated, isLoading, error, clearError } = useAuthStore();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated && !successMessage) navigate('/dashboard');
  }, [isAuthenticated]);

  useEffect(() => {
    clearError();
    setSuccessMessage(null);
  }, [mode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (mode === 'login') {
        await login(email, password);
        navigate('/dashboard');
      } else {
        await register(email, password, displayName, orgName || undefined);
        setSuccessMessage('Registration successful! Redirecting to dashboard...');
        setTimeout(() => {
          navigate('/dashboard');
        }, 1500);
      }
    } catch {
      /* error displayed by store */
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-bg" aria-hidden="true">
        <div className="auth-orb auth-orb--1" />
        <div className="auth-orb auth-orb--2" />
        <div className="auth-orb auth-orb--3" />
        <div className="auth-grid" />
      </div>

      <div className="auth-card">
        {/* Logo */}
        <div className="auth-logo">
          <div className="auth-logo-icon">
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="16" cy="16" r="16" fill="url(#authLogoGrad)" />
              <path d="M9 11h14M9 16h10M9 21h12" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
              <defs>
                <linearGradient id="authLogoGrad" x1="0" y1="0" x2="32" y2="32">
                  <stop stopColor="#6366f1" />
                  <stop offset="1" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <span className="auth-logo-text">Zapper AI</span>
        </div>

        <h1 className="auth-title">
          {mode === 'login' ? 'Welcome back' : 'Create your workspace'}
        </h1>
        <p className="auth-subtitle">
          {mode === 'login'
            ? 'Sign in to your meeting intelligence dashboard'
            : 'Join thousands of teams running smarter meetings'}
        </p>

        {/* Tabs */}
        <div className="auth-tabs" role="tablist">
          <button
            id="tab-login"
            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => setMode('login')}
            role="tab"
            aria-selected={mode === 'login'}
          >
            Sign In
          </button>
          <button
            id="tab-register"
            className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
            onClick={() => setMode('register')}
            role="tab"
            aria-selected={mode === 'register'}
          >
            Register
          </button>
        </div>

        <form id="auth-form" onSubmit={handleSubmit} noValidate>
          {mode === 'register' && (
            <>
              <div className="auth-field">
                <label className="auth-label" htmlFor="displayName">Full name</label>
                <input
                  id="displayName"
                  className="auth-input"
                  type="text"
                  placeholder="Rudra Patel"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  required
                  autoComplete="name"
                />
              </div>
              <div className="auth-field">
                <label className="auth-label" htmlFor="orgName">Organisation name <span className="auth-optional">(optional)</span></label>
                <input
                  id="orgName"
                  className="auth-input"
                  type="text"
                  placeholder="Acme Corp"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  autoComplete="organization"
                />
              </div>
            </>
          )}

          <div className="auth-field">
            <label className="auth-label" htmlFor="email">Email address</label>
            <input
              id="email"
              className="auth-input"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="password">Password</label>
            <div className="auth-password-wrapper">
              <input
                id="password"
                className="auth-input"
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />
              <button
                type="button"
                id="toggle-password"
                className="auth-eye-btn"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          {successMessage && (
            <div className="auth-success" role="alert">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              {successMessage}
            </div>
          )}

          {error && (
            <div className="auth-error" role="alert">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {error}
            </div>
          )}

          <button
            id="auth-submit"
            type="submit"
            className="auth-submit-btn"
            disabled={isLoading}
          >
            {isLoading ? (
              <span className="auth-spinner" aria-label="Loading" />
            ) : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        {mode === 'login' && (
          <p className="auth-footer-text">
            Don't have an account?{' '}
            <button id="switch-to-register" className="auth-link-btn" onClick={() => setMode('register')}>
              Register for free
            </button>
          </p>
        )}
        {mode === 'register' && (
          <p className="auth-footer-text">
            Already have an account?{' '}
            <button id="switch-to-login" className="auth-link-btn" onClick={() => setMode('login')}>
              Sign in
            </button>
          </p>
        )}

        <p className="auth-disclaimer">
          By continuing, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>

      <style>{`
        .auth-page {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #0b0f1a;
          padding: 2rem;
          position: relative;
          overflow: hidden;
          font-family: 'Inter', 'Outfit', system-ui, sans-serif;
        }

        .auth-bg { position: absolute; inset: 0; pointer-events: none; }

        .auth-orb {
          position: absolute;
          border-radius: 50%;
          filter: blur(80px);
          opacity: 0.25;
          animation: authFloat 8s ease-in-out infinite;
        }
        .auth-orb--1 {
          width: 600px; height: 600px;
          background: radial-gradient(circle, #6366f1, transparent);
          top: -200px; left: -200px;
          animation-delay: 0s;
        }
        .auth-orb--2 {
          width: 500px; height: 500px;
          background: radial-gradient(circle, #8b5cf6, transparent);
          bottom: -200px; right: -200px;
          animation-delay: 2s;
        }
        .auth-orb--3 {
          width: 300px; height: 300px;
          background: radial-gradient(circle, #06b6d4, transparent);
          top: 50%; left: 50%;
          transform: translate(-50%, -50%);
          animation-delay: 4s;
        }

        .auth-grid {
          position: absolute; inset: 0;
          background-image: linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
          background-size: 48px 48px;
        }

        @keyframes authFloat {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-20px); }
        }

        .auth-card {
          position: relative;
          z-index: 10;
          width: 100%;
          max-width: 420px;
          background: rgba(17, 24, 39, 0.85);
          backdrop-filter: blur(24px);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 20px;
          padding: 2.5rem;
          box-shadow: 0 0 60px rgba(99, 102, 241, 0.15), 0 32px 64px rgba(0,0,0,0.4);
          animation: authCardIn 0.5s cubic-bezier(.16,1,.3,1);
        }

        @keyframes authCardIn {
          from { opacity: 0; transform: translateY(24px) scale(0.97); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }

        .auth-logo {
          display: flex;
          align-items: center;
          gap: 0.625rem;
          margin-bottom: 1.75rem;
        }
        .auth-logo-icon { width: 40px; height: 40px; flex-shrink: 0; }
        .auth-logo-text {
          font-size: 1.25rem;
          font-weight: 700;
          background: linear-gradient(135deg, #6366f1, #a78bfa);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .auth-title {
          font-size: 1.625rem;
          font-weight: 700;
          color: #f9fafb;
          margin: 0 0 0.375rem;
          line-height: 1.2;
        }
        .auth-subtitle {
          font-size: 0.875rem;
          color: #6b7280;
          margin: 0 0 1.75rem;
        }

        .auth-tabs {
          display: flex;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 10px;
          padding: 4px;
          gap: 4px;
          margin-bottom: 1.5rem;
        }
        .auth-tab {
          flex: 1;
          background: transparent;
          border: none;
          border-radius: 8px;
          padding: 0.5rem 1rem;
          font-size: 0.875rem;
          font-weight: 500;
          color: #6b7280;
          cursor: pointer;
          transition: all 0.2s;
        }
        .auth-tab.active {
          background: rgba(99, 102, 241, 0.2);
          color: #a78bfa;
          box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.3);
        }
        .auth-tab:hover:not(.active) { color: #d1d5db; }

        .auth-field { margin-bottom: 1.125rem; }
        .auth-label {
          display: block;
          font-size: 0.8125rem;
          font-weight: 500;
          color: #9ca3af;
          margin-bottom: 0.375rem;
        }
        .auth-optional { color: #4b5563; font-weight: 400; }

        .auth-input {
          width: 100%;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 10px;
          padding: 0.6875rem 0.875rem;
          font-size: 0.9375rem;
          color: #f3f4f6;
          outline: none;
          transition: border-color 0.2s, box-shadow 0.2s;
          box-sizing: border-box;
        }
        .auth-input::placeholder { color: #4b5563; }
        .auth-input:focus {
          border-color: rgba(99, 102, 241, 0.5);
          box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
        }

        .auth-password-wrapper { position: relative; }
        .auth-password-wrapper .auth-input { padding-right: 2.75rem; }
        .auth-eye-btn {
          position: absolute;
          right: 0.75rem;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          padding: 0.25rem;
          color: #4b5563;
          cursor: pointer;
          display: flex;
          align-items: center;
          transition: color 0.2s;
        }
        .auth-eye-btn:hover { color: #9ca3af; }
        .auth-eye-btn svg { width: 18px; height: 18px; }

        .auth-success {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background: rgba(16, 185, 129, 0.12);
          border: 1px solid rgba(16, 185, 129, 0.25);
          border-radius: 10px;
          padding: 0.625rem 0.875rem;
          font-size: 0.8125rem;
          color: #34d399;
          margin-bottom: 1rem;
        }
        .auth-success svg { width: 15px; height: 15px; flex-shrink: 0; }

        .auth-error {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background: rgba(239, 68, 68, 0.12);
          border: 1px solid rgba(239, 68, 68, 0.25);
          border-radius: 10px;
          padding: 0.625rem 0.875rem;
          font-size: 0.8125rem;
          color: #f87171;
          margin-bottom: 1rem;
        }
        .auth-error svg { width: 15px; height: 15px; flex-shrink: 0; }

        .auth-submit-btn {
          width: 100%;
          padding: 0.8125rem;
          border: none;
          border-radius: 10px;
          background: linear-gradient(135deg, #6366f1, #8b5cf6);
          color: white;
          font-size: 0.9375rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          margin-top: 0.375rem;
          box-shadow: 0 4px 20px rgba(99, 102, 241, 0.35);
          letter-spacing: 0.01em;
        }
        .auth-submit-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 8px 28px rgba(99, 102, 241, 0.5);
        }
        .auth-submit-btn:active:not(:disabled) { transform: translateY(0); }
        .auth-submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }

        .auth-spinner {
          display: inline-block;
          width: 18px; height: 18px;
          border: 2px solid rgba(255,255,255,0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .auth-footer-text {
          text-align: center;
          font-size: 0.8125rem;
          color: #6b7280;
          margin: 1rem 0 0.375rem;
        }
        .auth-link-btn {
          background: none;
          border: none;
          color: #818cf8;
          cursor: pointer;
          font-size: 0.8125rem;
          font-weight: 500;
          padding: 0;
          transition: color 0.2s;
        }
        .auth-link-btn:hover { color: #a78bfa; text-decoration: underline; }

        .auth-disclaimer {
          text-align: center;
          font-size: 0.7rem;
          color: #374151;
          margin: 0.875rem 0 0;
        }
      `}</style>
    </div>
  );
}

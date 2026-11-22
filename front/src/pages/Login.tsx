import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff, LogIn } from 'lucide-react'
import { authApi } from '../api/auth'
import { useUserStore } from '../stores/useUserStore'
import { useLanguageStore } from '../stores/useLanguageStore'
import i18n from '../i18n'

export default function Login() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const login = useUserStore((s) => s.login)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) { setError('请输入用户名和密码'); return }
    setLoading(true)
    setError('')
    try {
      const res = await authApi.login(username, password)
      login(res.token, res.user)
      i18n.changeLanguage(useLanguageStore.getState().lang)
      navigate('/notes')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      if (detail && typeof detail === 'object') {
        const msg = Object.values(detail as Record<string, unknown>).flat().join('；')
        setError(msg || '登录失败，请检查用户名和密码')
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError('登录失败，请检查用户名和密码')
      }
    } finally {
      setLoading(false)
    }
  }

  const fillTestAccount = () => {
    setUsername('admin')
    setPassword('admin1234')
  }

  return (
    <div className="space-y-9">
      <div>
        <p className="editorial-kicker">Sign in · 登录</p>
        <h2 className="editorial-title mt-4 text-3xl">欢迎回来</h2>
        <div className="editorial-rule mt-5" />
      </div>

      <form onSubmit={handleLogin} className="space-y-7">
        {error && (
          <div className="border-l-2 border-[var(--color-danger)] bg-[var(--color-danger-bg)] px-4 py-3 text-sm text-[var(--color-danger)]">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label htmlFor="login-username" className="editorial-kicker block">{t('auth.username')}</label>
          <input
            id="login-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="editorial-input"
            placeholder={t('auth.username')}
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="login-password" className="editorial-kicker block">{t('auth.password')}</label>
          <div className="relative">
            <input
              id="login-password"
              type={showPwd ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="editorial-input pr-8"
              placeholder={t('auth.password')}
            />
            <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-0 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text)]">
              {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        <button type="submit" disabled={loading} className="editorial-btn h-11 w-full">
          {loading ? (
            <div className="w-4 h-4 animate-spin rounded-full border border-current border-t-transparent" />
          ) : (
            <LogIn size={14} />
          )}
          {t('auth.login')}
        </button>
      </form>

      <div className="flex flex-col items-start gap-3">
        <button onClick={fillTestAccount} className="text-xs text-[var(--color-text-tertiary)] underline-offset-4 transition-colors hover:text-[var(--color-accent)] hover:underline">
          {t('auth.testAccount')}
        </button>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {t('auth.noAccount')}{' '}
          <Link to="/register" className="text-[var(--color-accent)] underline decoration-1 underline-offset-4 hover:text-[var(--color-text)]">{t('auth.register')}</Link>
        </p>
      </div>
    </div>
  )
}

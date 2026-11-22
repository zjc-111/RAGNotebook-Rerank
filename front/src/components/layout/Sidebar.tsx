import { NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  FileText,
  MessageSquare,
  History,
  GraduationCap,
  Library,
  Network,
  Settings,
  User,
  Info,
  LogOut,
  Columns2,
} from 'lucide-react'
import { useUserStore } from '../../stores/useUserStore'
import { authApi } from '../../api/auth'

const navItems = [
  { path: '/notes', icon: FileText, labelKey: 'nav.notes' },
  { path: '/chat', icon: MessageSquare, labelKey: 'nav.chat' },
  { path: '/sessions', icon: History, labelKey: 'nav.sessions' },
  { path: '/review', icon: GraduationCap, labelKey: 'nav.review' },
  { path: '/knowledge', icon: Library, labelKey: 'nav.knowledge' },
  { path: '/graph', icon: Network, labelKey: 'nav.graph' },
]

const bottomItems = [
  { path: '/profile', icon: User, labelKey: 'nav.profile' },
  { path: '/settings', icon: Settings, labelKey: 'nav.settings' },
  { path: '/about', icon: Info, labelKey: 'nav.about' },
]

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const logout = useUserStore((s) => s.logout)

  const handleLogout = async () => {
    try { await authApi.logout() } catch { /* ignore */ }
    logout()
    navigate('/login')
  }

  const linkClass = (isActive: boolean) =>
    `relative flex items-center gap-3 px-3 py-2.5 text-sm transition-colors ${
      isActive
        ? 'text-[var(--color-text)] font-medium before:absolute before:left-0 before:top-2 before:bottom-2 before:w-px before:bg-[var(--color-accent)]'
        : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text)]'
    } ${collapsed ? 'justify-center' : ''}`

  return (
    <aside
      className={`flex flex-col border-r border-[var(--color-border)] bg-[var(--color-bg)] shrink-0 transition-all duration-300 ${
        collapsed ? 'w-16' : 'w-60'
      }`}
    >
      <div className={`border-b border-[var(--color-border)] ${collapsed ? 'px-3 py-5' : 'px-6 pb-5 pt-7'}`}>
        <div className="flex items-start justify-between gap-2">
          {!collapsed && (
            <div className="min-w-0">
              <p className="editorial-kicker">Editorial</p>
              <h1 className="editorial-title mt-1 truncate text-2xl">{t('app.name')}</h1>
            </div>
          )}
          <button
            onClick={onToggle}
            className="p-1 text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text)]"
            title={collapsed ? t('nav.expand') : t('nav.collapse')}
          >
            <Columns2 size={16} className={`transition-transform duration-300 ${collapsed ? 'rotate-180' : ''}`} />
          </button>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-5">
        {navItems.map(({ path, icon: Icon, labelKey }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/notes'}
            className={({ isActive }) => linkClass(isActive)}
            title={collapsed ? t(labelKey) : undefined}
          >
            <Icon size={17} strokeWidth={1.6} />
            {!collapsed && <span className="truncate">{t(labelKey)}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-0.5 border-t border-[var(--color-border)] px-3 py-4">
        {bottomItems.map(({ path, icon: Icon, labelKey }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) => linkClass(isActive)}
            title={collapsed ? t(labelKey) : undefined}
          >
            <Icon size={17} strokeWidth={1.6} />
            {!collapsed && <span className="truncate">{t(labelKey)}</span>}
          </NavLink>
        ))}
        <button
          onClick={handleLogout}
          className={`flex w-full items-center gap-3 px-3 py-2.5 text-sm text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-danger)] ${
            collapsed ? 'justify-center' : ''
          }`}
          title={collapsed ? t('nav.logout') : undefined}
        >
          <LogOut size={17} strokeWidth={1.6} />
          {!collapsed && <span className="truncate">{t('nav.logout')}</span>}
        </button>
      </div>
    </aside>
  )
}

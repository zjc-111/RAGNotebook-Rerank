import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

export default function AuthLayout() {
  const { t } = useTranslation()

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.05fr_1fr] bg-[var(--color-bg)]">
      {/* 左栏：杂志式品牌页 */}
      <section className="hidden lg:flex flex-col justify-between border-r border-[var(--color-border)] px-16 py-14 xl:px-24 xl:py-20">
        <div className="max-w-md">
          <p className="editorial-kicker">Featured · 个人知识库</p>
          <h1 className="editorial-title mt-7 text-6xl xl:text-7xl">{t('app.name')}</h1>
          <div className="editorial-rule mt-7" />
          <p className="mt-7 text-[15px] leading-[1.9] text-[var(--color-text-secondary)]">
            优雅的笔记排版，衬线标题与留白之美。
            把读过的、写下的，收进一个随时可以重新翻开的集子。
          </p>
          <div className="mt-10 flex items-center gap-4">
            <span className="editorial-rule w-10" />
            <span className="text-[13px] tracking-[0.06em] text-[var(--color-text-secondary)]">
              记录 · 检索 · 重读
            </span>
          </div>
        </div>

        <div>
          <p className="editorial-kicker mb-4">RAG · Knowledge Graph · Editorial Notes</p>
          <div className="flex h-2 w-full">
            <span className="flex-1 bg-[var(--color-text)]" />
            <span className="flex-1 bg-[var(--color-bg-tertiary)]" />
            <span className="flex-1 bg-[#6E7B8B]" />
            <span className="flex-1 bg-[#2C3038]" />
            <span className="flex-1 bg-[#8F6D70]" />
          </div>
        </div>
      </section>

      {/* 右栏：表单 */}
      <section className="flex items-center justify-center px-6 py-14 sm:px-12">
        <div className="w-full max-w-sm">
          <Outlet />
        </div>
      </section>
    </div>
  )
}

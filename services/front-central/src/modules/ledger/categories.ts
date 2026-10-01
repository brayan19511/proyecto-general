import type { Category } from './types'

// Categorías con sus subcategorías, alfabético.
export function categoryTree(categories: Category[]) {
  const byName = (a: Category, b: Category) => a.name.localeCompare(b.name, 'es')
  return categories
    .filter((c) => c.parent_id === null)
    .sort(byName)
    .map((parent) => ({ parent, children: categories.filter((c) => c.parent_id === parent.id).sort(byName) }))
}

// "OPERACIONES › GASTOS DIVERSOS" (o solo la categoría).
export function categoryPath(categories: Category[], id: string): string {
  const category = categories.find((c) => c.id === id)
  if (!category) return 'Categoría no encontrada'
  const parent = category.parent_id ? categories.find((c) => c.id === category.parent_id) : null
  return parent ? `${parent.name} › ${category.name}` : category.name
}

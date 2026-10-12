import { computed, ref } from 'vue'

const messages = {
	en: {
		hello: 'Hello', stations: 'My stations', next_up: 'Next up', waiting: 'waiting', no_tasks: 'No tasks assigned to you.',
		start: 'Start', open: 'Open', back: 'Back', save: 'Save', submit: 'Submit', assign: 'Assign',
		in_progress: 'In progress', complete: 'Finish job', pieces: 'pieces', quantity: 'Pieces finished',
		materials_used: 'Materials used', opening: 'Opening', closing: 'After these moves', real_count: 'Real count',
		moves: 'Pieces moved between grades', loss: 'Pieces lost or counted extra', add_move: 'Add a move',
		add_loss: 'Add a difference', reason: 'Reason', from: 'From', to: 'To', grade: 'Grade', total: 'Total',
		counts: 'Count the pieces of each grade', worker: 'Worker', choose_worker: 'Choose worker',
		unassigned: 'Jobs to assign', inspections: 'Inspections to assign', saved: 'Saved', done: 'Done',
		logout: 'Sign out', assign_work: 'Assign work', language: 'العربية', difference: 'Difference to explain',
	},
	ar: {
		hello: 'مرحبا', stations: 'محطاتي', next_up: 'التالي', waiting: 'بالانتظار', no_tasks: 'لا توجد مهام مخصصة لك.',
		start: 'ابدأ', open: 'افتح', back: 'رجوع', save: 'حفظ', submit: 'اعتماد', assign: 'تعيين',
		in_progress: 'قيد التنفيذ', complete: 'إنهاء المهمة', pieces: 'قطعة', quantity: 'القطع المنجزة',
		materials_used: 'المواد المستخدمة', opening: 'الافتتاحي', closing: 'بعد هذه التحركات', real_count: 'العدد الفعلي',
		moves: 'قطع انتقلت بين الدرجات', loss: 'قطع مفقودة أو زائدة', add_move: 'أضف حركة',
		add_loss: 'أضف فرقا', reason: 'السبب', from: 'من', to: 'إلى', grade: 'الدرجة', total: 'المجموع',
		counts: 'عدّ القطع لكل درجة', worker: 'العامل', choose_worker: 'اختر العامل',
		unassigned: 'مهام تحتاج تعيين', inspections: 'فحوصات تحتاج تعيين', saved: 'تم الحفظ', done: 'تم',
		logout: 'تسجيل الخروج', assign_work: 'توزيع العمل', language: 'English', difference: 'فرق يحتاج تفسيرا',
	},
}

export const locale = ref(localStorage.getItem('desar-locale') || 'en')
export const isRtl = computed(() => locale.value === 'ar')

export function t(key) {
	return messages[locale.value][key] ?? messages.en[key] ?? key
}

export function applyLocale() {
	document.documentElement.lang = locale.value
	document.documentElement.dir = isRtl.value ? 'rtl' : 'ltr'
}

export function toggleLocale() {
	locale.value = locale.value === 'en' ? 'ar' : 'en'
	localStorage.setItem('desar-locale', locale.value)
	applyLocale()
}

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, ErrorMessage, FormControl } from 'frappe-ui'
import { api, toJson } from '../api'
import { t } from '../i18n'
import { applyAdjustments, applyMovements, countsOf, totalOf } from '../gradeMath'
import GradeStepper from '../components/GradeStepper.vue'
import TopBar from '../components/TopBar.vue'

const props = defineProps({ name: String, user: Object })
const router = useRouter()
const form = ref(null)
const error = ref('')
const notice = ref('')

const load = async () => (form.value = await api('get_inspection', { name: props.name }))
onMounted(load)

const opening = computed(() => countsOf(form.value?.opening || []))
const moved = computed(() => applyMovements(opening.value, form.value?.movements || []))
const closing = computed(() => {
	if (!form.value) return {}
	if (form.value.entry_mode === 'Count' || form.value.entry_mode === 'Real Count') return countsOf(form.value.closing)
	return applyAdjustments(moved.value, form.value.adjustments)
})
const difference = computed(() => {
	if (form.value?.entry_mode !== 'Real Count') return []
	return form.value.grades.map((grade) => ({ grade, change: (closing.value[grade] || 0) - (moved.value[grade] || 0) })).filter((row) => row.change)
})
const reasonOptions = (kind) => (form.value?.reasons || []).filter((reason) => reason.kind === kind).map((reason) => ({ label: reason.name, value: reason.name }))
const gradeOptions = computed(() => (form.value?.grades || []).map((grade) => ({ label: grade, value: grade })))

const closingRow = (grade) => form.value.closing.find((row) => row.grade_code === grade)
const adjustmentFor = (grade) => form.value.adjustments.find((row) => row.grade_code === grade)

async function save() {
	error.value = ''
	try {
		const payload = { name: props.name, closing: toJson(form.value.closing), movements: toJson(form.value.movements), adjustments: toJson(form.value.adjustments) }
		form.value = await api('save_inspection', payload)
		notice.value = t('saved')
	} catch (failure) {
		error.value = failure.messages?.join(' ') || failure.message
		return false
	}
	return true
}

async function submit() {
	if (!(await save())) return
	try {
		await api('submit_inspection', { name: props.name })
		router.replace('/')
	} catch (failure) {
		error.value = failure.messages?.join(' ') || failure.message
	}
}
</script>

<template>
	<TopBar :user="user" :title="form ? `${form.stage} · ${form.roll_ticket}` : ''" back />
	<main v-if="form" class="mx-auto grid max-w-5xl grid-cols-1 gap-6 p-6 md:grid-cols-2">
		<section class="flex flex-col gap-4">
			<template v-if="form.entry_mode === 'Count'">
				<div class="text-sm font-semibold text-ink-gray-6">{{ t('counts').toUpperCase() }}</div>
				<div class="flex gap-3">
					<GradeStepper v-for="grade in form.grades" :key="grade" :grade="grade" :model-value="closingRow(grade).qty" @update:model-value="closingRow(grade).qty = $event" />
				</div>
			</template>
			<template v-else>
				<div class="text-sm font-semibold text-ink-gray-6">{{ t('opening').toUpperCase() }}</div>
				<div class="flex gap-3"><GradeStepper v-for="grade in form.grades" :key="grade" :grade="grade" :model-value="opening[grade] || 0" readonly /></div>
				<div class="text-sm font-semibold text-ink-gray-6">{{ t('moves').toUpperCase() }}</div>
				<div v-for="(move, index) in form.movements" :key="index" class="flex flex-wrap items-center gap-2 rounded-xl border border-outline-gray-2 bg-surface-white p-3">
					<FormControl v-model="move.from_grade" type="select" :options="gradeOptions" class="w-24" />
					<span class="text-xl">→</span>
					<FormControl v-model="move.to_grade" type="select" :options="gradeOptions" class="w-24" />
					<FormControl v-model.number="move.qty" type="number" class="w-24" />
					<FormControl v-model="move.reason" type="select" :options="reasonOptions('Movement')" class="min-w-48 flex-1" />
					<Button variant="ghost" @click="form.movements.splice(index, 1)">✕</Button>
				</div>
				<Button size="lg" variant="outline" @click="form.movements.push({ from_grade: 'B', to_grade: 'A', qty: 1, reason: '' })">{{ t('add_move') }}</Button>
				<template v-if="form.entry_mode === 'Movement'">
					<div class="text-sm font-semibold text-ink-gray-6">{{ t('loss').toUpperCase() }}</div>
					<div v-for="(row, index) in form.adjustments" :key="index" class="flex flex-wrap items-center gap-2 rounded-xl border border-outline-gray-2 bg-surface-white p-3">
						<FormControl v-model="row.grade_code" type="select" :options="gradeOptions" class="w-24" />
						<FormControl v-model.number="row.qty" type="number" class="w-24" />
						<FormControl v-model="row.reason" type="select" :options="reasonOptions('Loss')" class="min-w-48 flex-1" />
						<Button variant="ghost" @click="form.adjustments.splice(index, 1)">✕</Button>
					</div>
					<Button size="lg" variant="outline" @click="form.adjustments.push({ grade_code: 'B', qty: -1, reason: '' })">{{ t('add_loss') }}</Button>
				</template>
			</template>
		</section>
		<section class="flex flex-col gap-4">
			<template v-if="form.entry_mode === 'Real Count'">
				<div class="text-sm font-semibold text-ink-gray-6">{{ t('real_count').toUpperCase() }}</div>
				<div class="flex gap-3"><GradeStepper v-for="grade in form.grades" :key="grade" :grade="grade" :model-value="closingRow(grade).qty" @update:model-value="closingRow(grade).qty = $event" /></div>
				<div v-if="difference.length" class="flex flex-col gap-2 rounded-xl border-2 border-outline-amber-2 bg-surface-amber-1 p-4">
					<div class="font-semibold text-ink-gray-9">{{ t('difference') }}</div>
					<div v-for="row in difference" :key="row.grade" class="flex items-center gap-3">
						<span class="w-20 font-semibold">{{ row.grade }} {{ row.change > 0 ? '+' : '' }}{{ row.change }}</span>
						<FormControl type="select" :options="reasonOptions(row.change < 0 ? 'Loss' : 'Count Gain')" :model-value="adjustmentFor(row.grade)?.reason" class="flex-1"
							@update:model-value="form.adjustments = [...form.adjustments.filter((a) => a.grade_code !== row.grade), { grade_code: row.grade, qty: row.change, reason: $event }]" />
					</div>
				</div>
			</template>
			<template v-else-if="form.entry_mode === 'Movement'">
				<div class="text-sm font-semibold text-ink-gray-6">{{ t('closing').toUpperCase() }}</div>
				<div class="flex gap-3"><GradeStepper v-for="grade in form.grades" :key="grade" :grade="grade" :model-value="closing[grade] || 0" readonly /></div>
			</template>
			<div class="text-lg text-ink-gray-8">{{ t('total') }}: {{ totalOf(closing) }}</div>
			<ErrorMessage :message="error" />
			<div v-if="notice" class="text-ink-green-3">{{ notice }}</div>
			<div class="mt-auto flex gap-3">
				<Button size="xl" variant="outline" class="!h-16 flex-1" @click="save">{{ t('save') }}</Button>
				<Button size="xl" variant="solid" theme="gray" class="!h-16 flex-[1.4]" @click="submit">{{ t('submit') }}</Button>
			</div>
		</section>
	</main>
</template>

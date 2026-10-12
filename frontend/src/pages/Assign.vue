<script setup>
import { onMounted, ref } from 'vue'
import { Badge, Button, FormControl } from 'frappe-ui'
import { api } from '../api'
import { t } from '../i18n'
import TopBar from '../components/TopBar.vue'

defineProps({ user: Object })
const jobs = ref([])
const rolls = ref([])
const workers = ref([])
const chosen = ref({})

async function load() {
	;[jobs.value, rolls.value, workers.value] = await Promise.all([api('unassigned_tasks'), api('inspection_candidates'), api('workers')])
}
onMounted(load)

const workerOptions = () => workers.value.map((worker) => ({ label: worker.full_name || worker.name, value: worker.name }))

async function assignJob(job) {
	await api('assign_job_card', { job_card: job.name, user: chosen.value[job.name] })
	await load()
}
async function assignInspection(roll) {
	await api('assign_inspection', { roll_ticket: roll.roll_ticket, stage: roll.stage, user: chosen.value[roll.roll_ticket] })
	await load()
}
</script>

<template>
	<TopBar :user="user" :title="t('assign_work')" back />
	<main class="mx-auto flex max-w-4xl flex-col gap-6 p-6">
		<section class="flex flex-col gap-3">
			<div class="text-sm font-semibold text-ink-gray-6">{{ t('unassigned').toUpperCase() }}</div>
			<div v-for="job in jobs" :key="job.name" class="flex items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-white p-4">
				<div class="min-w-0 flex-1"><div class="text-lg font-semibold">{{ job.title }}</div><div class="text-ink-gray-6">{{ job.subtitle }}</div></div>
				<Badge v-if="job.assigned_to.length" :label="job.assigned_to.join(', ')" theme="blue" />
				<FormControl v-model="chosen[job.name]" type="select" :options="workerOptions()" :placeholder="t('choose_worker')" class="w-48" />
				<Button variant="solid" theme="gray" size="lg" :disabled="!chosen[job.name]" @click="assignJob(job)">{{ t('assign') }}</Button>
			</div>
		</section>
		<section class="flex flex-col gap-3">
			<div class="text-sm font-semibold text-ink-gray-6">{{ t('inspections').toUpperCase() }}</div>
			<div v-for="roll in rolls" :key="roll.roll_ticket" class="flex items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-white p-4">
				<div class="min-w-0 flex-1"><div class="text-lg font-semibold">{{ roll.roll_ticket }}</div><div class="text-ink-gray-6">{{ roll.stage }} · {{ roll.work_order }}</div></div>
				<FormControl v-model="chosen[roll.roll_ticket]" type="select" :options="workerOptions()" :placeholder="t('choose_worker')" class="w-48" />
				<Button variant="solid" theme="gray" size="lg" :disabled="!chosen[roll.roll_ticket]" @click="assignInspection(roll)">{{ t('assign') }}</Button>
			</div>
		</section>
	</main>
</template>

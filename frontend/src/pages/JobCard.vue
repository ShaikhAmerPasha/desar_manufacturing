<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, ErrorMessage, FormControl } from 'frappe-ui'
import { api, toJson } from '../api'
import { t } from '../i18n'
import TopBar from '../components/TopBar.vue'

const props = defineProps({ name: String, user: Object })
const router = useRouter()
const job = ref(null)
const quantity = ref(0)
const used = ref({})
const error = ref('')

async function load() {
	job.value = await api('get_job_card', { name: props.name })
	quantity.value = job.value.qty
}
onMounted(load)

async function run(action) {
	error.value = ''
	try {
		await action()
	} catch (failure) {
		error.value = failure.messages?.join(' ') || failure.message
	}
}

const start = () => run(async () => { await api('start_job', { job_card: props.name }); await load() })
const finish = () => run(async () => {
	const consumption = Object.entries(used.value).filter(([, qty]) => qty > 0).map(([item_code, qty]) => ({ item_code, qty: Number(qty) }))
	await api('complete_job', { job_card: props.name, completed_qty: quantity.value, consumption: toJson(consumption) })
	router.replace('/')
})
</script>

<template>
	<TopBar :user="user" :title="job?.operation" back />
	<main v-if="job" class="mx-auto flex max-w-2xl flex-col gap-5 p-6">
		<div class="rounded-xl border border-outline-gray-2 bg-surface-white p-5 text-lg text-ink-gray-8">
			{{ job.beam }} · {{ job.workstation }} · {{ job.qty }} {{ t('pieces') }}
		</div>
		<Button v-if="!job.started_at" size="xl" variant="solid" theme="gray" class="!h-16 text-xl" @click="start">{{ t('start') }}</Button>
		<template v-else>
			<FormControl v-model="quantity" type="number" size="lg" :label="t('quantity')" />
			<div v-if="job.materials.length" class="flex flex-col gap-3">
				<div class="text-sm font-semibold text-ink-gray-6">{{ t('materials_used').toUpperCase() }}</div>
				<div v-for="item in job.materials" :key="item.item_code" class="flex items-center gap-3">
					<div class="flex-1 text-lg text-ink-gray-9">{{ item.item_name || item.item_code }}<span class="text-sm text-ink-gray-6"> · {{ item.planned_qty.toFixed(2) }} {{ item.uom }}</span></div>
					<FormControl v-model="used[item.item_code]" type="number" size="lg" class="w-32" />
				</div>
			</div>
			<ErrorMessage :message="error" />
			<Button size="xl" variant="solid" theme="gray" class="!h-16 text-xl" @click="finish">{{ t('complete') }}</Button>
		</template>
		<ErrorMessage v-if="!job.started_at" :message="error" />
	</main>
</template>

import { createRouter, createWebHistory } from 'vue-router'

const routes = [
	{ path: '/', name: 'Tasks', component: () => import('./pages/Tasks.vue') },
	{ path: '/job/:name', name: 'Job', component: () => import('./pages/JobCard.vue'), props: true },
	{ path: '/inspect/:name', name: 'Inspect', component: () => import('./pages/Inspection.vue'), props: true },
	{ path: '/assign', name: 'Assign', component: () => import('./pages/Assign.vue') },
]

export default createRouter({ history: createWebHistory('/shop-floor'), routes })

import { call } from 'frappe-ui'

const BASE = 'desar_manufacturing.api.shop_floor.'

export const api = (method, params = {}) => call(BASE + method, params)

export function toJson(value) {
	return JSON.stringify(value)
}

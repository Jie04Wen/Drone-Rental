import {mount} from '@vue/test-utils'
import {describe, expect, it} from 'vitest'
import DroneCard from '../DroneCard.vue'

const mountCard = (drone) => mount(DroneCard, {
    props: {
        drone: {
            model: '测试设备',
            brand: '测试品牌',
            stock: 1,
            status: 1,
            pricePerDay: 100,
            ...drone
        }
    },
    global: {
        stubs: {
            'el-icon': true,
            StatusTag: {
                props: ['text', 'type'],
                template: '<span :data-type="type">{{ text }}</span>'
            }
        }
    }
})

describe('DroneCard status', () => {
    it('shows out of stock whenever inventory is zero', () => {
        const wrapper = mountCard({stock: 0, status: 1})
        expect(wrapper.text()).toContain('缺货')
        expect(wrapper.find('[data-type="error"]').exists()).toBe(true)
    })

    it('gives zero inventory priority over maintenance', () => {
        expect(mountCard({stock: 0, status: 2}).text()).toContain('缺货')
    })

    it('shows maintenance when inventory remains', () => {
        const wrapper = mountCard({stock: 2, status: 2})
        expect(wrapper.text()).toContain('维护中')
        expect(wrapper.find('[data-type="warning"]').exists()).toBe(true)
    })
})

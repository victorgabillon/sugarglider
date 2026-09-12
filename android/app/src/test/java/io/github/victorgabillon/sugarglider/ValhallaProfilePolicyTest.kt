package io.github.victorgabillon.sugarglider

import com.valhalla.api.models.BicycleCostingOptions
import com.valhalla.api.models.CostingModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class ValhallaProfilePolicyTest {
    @Test
    fun everyPublicProfileHasOneDeterministicTypedPolicy() {
        val policies = LocalRouteProfile.entries.map(ValhallaProfilePolicies::forProfile)

        assertEquals(LocalRouteProfile.entries, policies.map { it.profile })
        assertEquals(6, policies.map { it.costingModel to it.costingOptions }.distinct().size)
        policies.forEach { policy ->
            when (policy.profile.accessMode) {
                LocalRouteAccessMode.FOOT -> {
                    assertEquals(CostingModel.pedestrian, policy.costingModel)
                    assertNotNull(policy.costingOptions.pedestrian)
                    assertNull(policy.costingOptions.bicycle)
                }
                LocalRouteAccessMode.BICYCLE -> {
                    assertEquals(CostingModel.bicycle, policy.costingModel)
                    assertNotNull(policy.costingOptions.bicycle)
                    assertNull(policy.costingOptions.pedestrian)
                }
            }
        }
    }

    @Test
    fun pedestrianPoliciesExpressDifferentTrailAndTechnicalIntent() {
        val trailRun = ValhallaProfilePolicies.forProfile(LocalRouteProfile.TRAIL_RUN)
            .costingOptions.pedestrian!!
        val hike = ValhallaProfilePolicies.forProfile(LocalRouteProfile.HIKE)
            .costingOptions.pedestrian!!

        assertNotEquals(trailRun, hike)
        assertEquals(1, trailRun.maxHikingDifficulty)
        assertEquals(3, hike.maxHikingDifficulty)
        assertEquals(120, trailRun.stepPenalty)
        assertEquals(30, hike.stepPenalty)
    }

    @Test
    fun bicyclePoliciesUseFourDistinctTypedBicycleIntents() {
        val city = bicycle(LocalRouteProfile.CITY_BIKE)
        val gravel = bicycle(LocalRouteProfile.GRAVEL_BIKE)
        val mountain = bicycle(LocalRouteProfile.MOUNTAIN_BIKE)
        val road = bicycle(LocalRouteProfile.ROAD_BIKE)

        assertEquals(BicycleCostingOptions.BicycleType.Hybrid, city.bicycleType)
        assertEquals(BicycleCostingOptions.BicycleType.Cross, gravel.bicycleType)
        assertEquals(BicycleCostingOptions.BicycleType.Mountain, mountain.bicycleType)
        assertEquals(BicycleCostingOptions.BicycleType.Road, road.bicycleType)
        assertEquals(4, listOf(city, gravel, mountain, road).distinct().size)
        assertEquals(0.0, mountain.avoidBadSurfaces!!, 0.0)
        assertEquals(0.95, road.avoidBadSurfaces!!, 0.0)
    }

    private fun bicycle(profile: LocalRouteProfile): BicycleCostingOptions =
        ValhallaProfilePolicies.forProfile(profile).costingOptions.bicycle!!
}

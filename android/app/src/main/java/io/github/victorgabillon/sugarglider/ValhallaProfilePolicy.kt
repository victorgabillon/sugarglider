package io.github.victorgabillon.sugarglider

import com.valhalla.api.models.BicycleCostingOptions
import com.valhalla.api.models.CostingModel
import com.valhalla.api.models.CostingOptions
import com.valhalla.api.models.PedestrianCostingOptions

internal data class ValhallaProfilePolicy(
    val profile: LocalRouteProfile,
    val costingModel: CostingModel,
    val costingOptions: CostingOptions,
)

internal object ValhallaProfilePolicies {
    private val policies = listOf(
        pedestrianPolicy(
            LocalRouteProfile.TRAIL_RUN,
            walkingSpeed = 9,
            stepPenalty = 120,
            useTracks = 0.65,
            useHills = 0.45,
            maxHikingDifficulty = 1,
        ),
        pedestrianPolicy(
            LocalRouteProfile.HIKE,
            walkingSpeed = 5,
            stepPenalty = 30,
            useTracks = 1.0,
            useHills = 0.75,
            maxHikingDifficulty = 3,
        ),
        bicyclePolicy(
            LocalRouteProfile.CITY_BIKE,
            bicycleType = BicycleCostingOptions.BicycleType.Hybrid,
            cyclingSpeed = 18,
            useRoads = 0.25,
            useHills = 0.35,
            avoidBadSurfaces = 0.85,
        ),
        bicyclePolicy(
            LocalRouteProfile.GRAVEL_BIKE,
            bicycleType = BicycleCostingOptions.BicycleType.Cross,
            cyclingSpeed = 20,
            useRoads = 0.35,
            useHills = 0.5,
            avoidBadSurfaces = 0.35,
        ),
        bicyclePolicy(
            LocalRouteProfile.MOUNTAIN_BIKE,
            bicycleType = BicycleCostingOptions.BicycleType.Mountain,
            cyclingSpeed = 16,
            useRoads = 0.15,
            useHills = 0.75,
            avoidBadSurfaces = 0.0,
        ),
        bicyclePolicy(
            LocalRouteProfile.ROAD_BIKE,
            bicycleType = BicycleCostingOptions.BicycleType.Road,
            cyclingSpeed = 25,
            useRoads = 0.8,
            useHills = 0.5,
            avoidBadSurfaces = 0.95,
        ),
    ).associateBy(ValhallaProfilePolicy::profile)

    init {
        check(policies.keys == LocalRouteProfile.entries.toSet())
        check(policies.values.map { it.costingModel to it.costingOptions }.distinct().size == 6)
    }

    fun forProfile(profile: LocalRouteProfile): ValhallaProfilePolicy =
        checkNotNull(policies[profile])

    private fun pedestrianPolicy(
        profile: LocalRouteProfile,
        walkingSpeed: Int,
        stepPenalty: Int,
        useTracks: Double,
        useHills: Double,
        maxHikingDifficulty: Int,
    ): ValhallaProfilePolicy {
        check(profile.accessMode == LocalRouteAccessMode.FOOT)
        return ValhallaProfilePolicy(
            profile = profile,
            costingModel = CostingModel.pedestrian,
            costingOptions = CostingOptions(
                pedestrian = PedestrianCostingOptions(
                    walkingSpeed = walkingSpeed,
                    stepPenalty = stepPenalty,
                    useTracks = useTracks,
                    useHills = useHills,
                    maxHikingDifficulty = maxHikingDifficulty,
                ),
            ),
        )
    }

    private fun bicyclePolicy(
        profile: LocalRouteProfile,
        bicycleType: BicycleCostingOptions.BicycleType,
        cyclingSpeed: Int,
        useRoads: Double,
        useHills: Double,
        avoidBadSurfaces: Double,
    ): ValhallaProfilePolicy {
        check(profile.accessMode == LocalRouteAccessMode.BICYCLE)
        return ValhallaProfilePolicy(
            profile = profile,
            costingModel = CostingModel.bicycle,
            costingOptions = CostingOptions(
                bicycle = BicycleCostingOptions(
                    bicycleType = bicycleType,
                    cyclingSpeed = cyclingSpeed,
                    useRoads = useRoads,
                    useHills = useHills,
                    avoidBadSurfaces = avoidBadSurfaces,
                ),
            ),
        )
    }
}

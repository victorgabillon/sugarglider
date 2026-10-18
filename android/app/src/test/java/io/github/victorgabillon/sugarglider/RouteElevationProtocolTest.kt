package io.github.victorgabillon.sugarglider

import kotlin.math.ceil
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RouteElevationProtocolTest {
    private val id="web-${"a".repeat(32)}-1"
    private fun value(distance: Double=100.0): JSONObject {
        val interval=maxOf(50.0,distance/2047);val count=if(distance>102350)2048 else ceil(distance/50).toInt()+1
        return JSONObject().put("schema_version",1).put("request_id",id).put("type","route_elevation").put("elevation_version",1)
            .put("operation_id","b".repeat(32)).put("candidate_id","geometry:"+"c".repeat(64)).put("profile","hike")
            .put("geometry_sha256","d".repeat(64)).put("distance_m",distance).put("regional_reference",syntheticRegionalRoutingReference().toJson())
            .put("sampling_interval_m",interval).put("samples",JSONArray((0 until count).map { JSONArray(listOf(if(it==count-1)distance else it*interval,48.88,2.08)) }))
    }
    @Test fun strictBoundedRequestsAndLongRouteBudget() {
        for(distance in listOf(0.001,50.0,100.0,102350.0,102350.001,199999.9,200000.0)) {
            val parsed=BridgeProtocol.parse(value(distance).toString());assertTrue("$distance",parsed is BridgeRequest.RouteElevation)
            val request=(parsed as BridgeRequest.RouteElevation).elevation
            assertTrue(request.positions.size<=2048);assertTrue(request.interval<=100);assertEquals(distance,request.positions.last().first,0.0)
            assertTrue(BundledShellPolicy.acceptsRequest(parsed));assertFalse(BundledShellPolicy.acceptsOrigin(parsed,"https://other.example"))
        }
    }
    @Test fun malformedInputsFailExplicitly() {
        val mutations=listOf<(JSONObject)->Unit>(
            {it.put("extra",true)},{it.put("schema_version","1")},{it.put("elevation_version",1.5)},
            {it.put("operation_id","../escape")},{it.put("candidate_id","other")},{it.put("profile","pedestrian")},
            {it.put("geometry_sha256","z".repeat(64))},{it.put("distance_m",200001)}, {it.put("sampling_interval_m",100)},
            {it.put("samples",JSONArray())},{it.getJSONArray("samples").getJSONArray(1).put(0,0)},
            {it.getJSONArray("samples").getJSONArray(1).put(1,"48.0")},{it.getJSONArray("samples").getJSONArray(1).put(2,181)},
            {it.getJSONObject("regional_reference").getJSONObject("elevation").put("component_id","../wrong")})
        for(change in mutations){val input=value();change(input);assertTrue(input.toString(),BridgeProtocol.parse(input.toString()) is BridgeRequest.RejectedRouteElevation)}
        assertNull(BridgeProtocol.parse(value().put("padding","x".repeat(MAX_ELEVATION_REQUEST_CHARS)).toString()))
    }
    @Test fun calculationUsesWholeComponentAndDrainsCancellation() {
        val parsed=BridgeProtocol.parse(value().toString()) as BridgeRequest.RouteElevation
        var calls=0;var cancelled=false
        var heights:List<Double?> = listOf(0.0,30.0,0.0)
        var heightReference = ELEVATION_HEIGHT_REFERENCE
        val engine=object:NativeOfflineEngine {
            override fun close()=Unit
            override fun capabilities(reference:RegionalRoutingPackReference?):NativeRouteCapabilities=error("unused")
            override fun route(request:NativeRouteRequest):NativeRouteResult=error("elevation must never reroute")
            override fun height(reference:RegionalRoutingPackReference,points:List<LocalRouteCoordinate>,id:String):NativeHeightResult {
                calls++;return NativeHeightResult.Success(reference,heights,1,0,false,heightReference)
            }
        }
        val result=JSONObject(RouteElevationProtocol.execute(id,parsed.elevation,engine){cancelled})
        assertEquals("local_elevation_result",result.getString("type"));val analysis=result.getJSONObject("analysis")
        assertEquals(parsed.elevation.reference.elevation.manifest.sha256,analysis.getString("source_sha256"))
        assertEquals(15.0,analysis.getDouble("total_ascent_m"),1e-7)
        assertEquals(parsed.elevation.candidateId,result.getString("candidate_id"))
        assertEquals(ELEVATION_HEIGHT_REFERENCE, analysis.getString("height_reference"))
        heightReference = ELEVATION_EGM96_REFERENCE
        val documented = JSONObject(RouteElevationProtocol.execute(id,parsed.elevation,engine){false}).getJSONObject("analysis")
        assertEquals(ELEVATION_EGM96_REFERENCE, documented.getString("height_reference"))
        assertEquals(analysis.getDouble("total_ascent_m"), documented.getDouble("total_ascent_m"), 0.0)
        heightReference = ELEVATION_IGN69_REFERENCE
        val ign = JSONObject(RouteElevationProtocol.execute(id,parsed.elevation,engine){false}).getJSONObject("analysis")
        assertEquals(ELEVATION_IGN69_REFERENCE, ign.getString("height_reference"))
        assertEquals(analysis.getDouble("total_ascent_m"), ign.getDouble("total_ascent_m"), 0.0)
        heights=listOf(0.0,null,0.0)
        val partial=JSONObject(RouteElevationProtocol.execute(id,parsed.elevation,engine){false}).getJSONObject("analysis")
        assertEquals("partial",partial.getString("coverage"));assertTrue(partial.isNull("total_ascent_m"));assertTrue(partial.getJSONArray("samples").getJSONObject(1).isNull("height_m"))
        heights=listOf(null,null,null)
        val absent=JSONObject(RouteElevationProtocol.execute(id,parsed.elevation,engine){false}).getJSONObject("analysis")
        assertEquals("unavailable",absent.getString("coverage"));assertTrue(absent.isNull("minimum_height_m"))
        cancelled=true
        assertEquals("elevation_cancelled",JSONObject(RouteElevationProtocol.execute(id,parsed.elevation,engine){cancelled}).getString("code"));assertEquals(5,calls)
        var checks=0
        assertEquals("elevation_cancelled",JSONObject(RouteElevationProtocol.execute(id,parsed.elevation,engine){++checks>=2}).getString("code"));assertEquals(6,calls)
    }
}

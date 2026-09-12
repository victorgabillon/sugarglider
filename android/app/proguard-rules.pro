# Release shrinking is currently disabled. The production Valhalla dependencies
# include Moshi reflection and JNI; enable R8 only after auditing their keep rules
# and repeating the native planning/export acceptance on the shrunk artifact.

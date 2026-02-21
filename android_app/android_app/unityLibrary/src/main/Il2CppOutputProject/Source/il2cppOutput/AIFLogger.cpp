#include "pch-cpp.hpp"





template <typename R>
struct VirtualFuncInvoker0
{
	typedef R (*Func)(void*, const RuntimeMethod*);

	static inline R Invoke (Il2CppMethodSlot slot, RuntimeObject* obj)
	{
		const VirtualInvokeData& invokeData = il2cpp_codegen_get_virtual_invoke_data(slot, obj);
		return ((Func)invokeData.methodPtr)(obj, invokeData.method);
	}
};

struct Dictionary_2_t14FE4A752A83D53771C584E4C8D14E01F2AFD7BA;
struct Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE;
struct IEqualityComparer_1_t0C79004BFE79D9DBCE6C2250109D31D468A9A68E;
struct KeyCollection_t555B8656568D51D28955442D71A19D8860BFF88C;
struct ValueCollection_t6E6C24D8CE99E9A850AB95B69939CBBA2CB9E7D9;
struct EntryU5BU5D_t7C07FADA3D121BF791083230AC898F54129541C8;
struct ByteU5BU5D_tA6237BF417AE52AD70CFB4EF24A7A82613DF9031;
struct Int32U5BU5D_t19C97395396A72ECAF310612F0760F165060314C;
struct ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918;
struct TypeU5BU5D_t97234E1129B564EB38B8D85CAC2AD8B5B9522FFB;
struct Binder_t91BFCE95A7057FADF4D8A1A342AFE52872246235;
struct MemberFilter_tF644F1AE82F611B677CE1964D5A3277DDA21D553;
struct String_t;
struct Type_t;
struct Void_t4861ACF8F4594C3437BB48B6E56783494B843915;

IL2CPP_EXTERN_C RuntimeClass* AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var;
IL2CPP_EXTERN_C RuntimeClass* Debug_t8394C7EEAECA3689C2C9B9DE9C7166D73596276F_il2cpp_TypeInfo_var;
IL2CPP_EXTERN_C RuntimeClass* Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE_il2cpp_TypeInfo_var;
IL2CPP_EXTERN_C RuntimeClass* Math_tEB65DE7CA8B083C412C969C92981C030865486CE_il2cpp_TypeInfo_var;
IL2CPP_EXTERN_C RuntimeClass* ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918_il2cpp_TypeInfo_var;
IL2CPP_EXTERN_C String_t* _stringLiteral1A61CB167BC3EB3F99E232409244273D3BBED824;
IL2CPP_EXTERN_C String_t* _stringLiteral86953B386E543DC5AFB5CC6DFBD735EF7DAE369D;
IL2CPP_EXTERN_C const RuntimeMethod* Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC_RuntimeMethod_var;
IL2CPP_EXTERN_C const RuntimeMethod* Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F_RuntimeMethod_var;
IL2CPP_EXTERN_C const RuntimeMethod* Dictionary_2__ctor_mFAF23CD29002CAB23492293F8C8B56962DE7A0B6_RuntimeMethod_var;
IL2CPP_EXTERN_C const RuntimeMethod* Dictionary_2_get_Item_m3359894DA1EF277B87D6220E9C380C4C01AE6008_RuntimeMethod_var;
IL2CPP_EXTERN_C const RuntimeMethod* Dictionary_2_set_Item_mDA78A8299D16DD1B42B93F0C63BE2D9CE92F8A00_RuntimeMethod_var;

struct ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918;

IL2CPP_EXTERN_C_BEGIN
IL2CPP_EXTERN_C_END

#ifdef __clang__
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Winvalid-offsetof"
#pragma clang diagnostic ignored "-Wunused-variable"
#endif
struct U3CModuleU3E_tEA29D7C27D97B3E7E5C39D7E443F1F2EFCCE3ACA 
{
};
struct Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE  : public RuntimeObject
{
	Int32U5BU5D_t19C97395396A72ECAF310612F0760F165060314C* ____buckets;
	EntryU5BU5D_t7C07FADA3D121BF791083230AC898F54129541C8* ____entries;
	int32_t ____count;
	int32_t ____freeList;
	int32_t ____freeCount;
	int32_t ____version;
	RuntimeObject* ____comparer;
	KeyCollection_t555B8656568D51D28955442D71A19D8860BFF88C* ____keys;
	ValueCollection_t6E6C24D8CE99E9A850AB95B69939CBBA2CB9E7D9* ____values;
	RuntimeObject* ____syncRoot;
};
struct AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C  : public RuntimeObject
{
};
struct MemberInfo_t  : public RuntimeObject
{
};
struct String_t  : public RuntimeObject
{
	int32_t ____stringLength;
	Il2CppChar ____firstChar;
};
struct ValueType_t6D9B272BD21782F0A9A14F2E41F85A50E97A986F  : public RuntimeObject
{
};
struct ValueType_t6D9B272BD21782F0A9A14F2E41F85A50E97A986F_marshaled_pinvoke
{
};
struct ValueType_t6D9B272BD21782F0A9A14F2E41F85A50E97A986F_marshaled_com
{
};
struct Boolean_t09A6377A54BE2F9E6985A8149F19234FD7DDFE22 
{
	bool ___m_value;
};
struct Char_t521A6F19B456D956AF452D926C32709DC03D6B17 
{
	Il2CppChar ___m_value;
};
struct Double_tE150EF3D1D43DEE85D533810AB4C742307EEDE5F 
{
	double ___m_value;
};
struct Int32_t680FF22E76F6EFAD4375103CBBFFA0421349384C 
{
	int32_t ___m_value;
};
struct IntPtr_t 
{
	void* ___m_value;
};
struct Single_t4530F2FF86FCB0DC29F35385CA1BD21BE294761C 
{
	float ___m_value;
};
struct Void_t4861ACF8F4594C3437BB48B6E56783494B843915 
{
	union
	{
		struct
		{
		};
		uint8_t Void_t4861ACF8F4594C3437BB48B6E56783494B843915__padding[1];
	};
};
struct RuntimeTypeHandle_t332A452B8B6179E4469B69525D0FE82A88030F7B 
{
	intptr_t ___value;
};
struct Type_t  : public MemberInfo_t
{
	RuntimeTypeHandle_t332A452B8B6179E4469B69525D0FE82A88030F7B ____impl;
};
struct AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields
{
	Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* ___typeColorDictionary;
};
struct String_t_StaticFields
{
	String_t* ___Empty;
};
struct Boolean_t09A6377A54BE2F9E6985A8149F19234FD7DDFE22_StaticFields
{
	String_t* ___TrueString;
	String_t* ___FalseString;
};
struct Char_t521A6F19B456D956AF452D926C32709DC03D6B17_StaticFields
{
	ByteU5BU5D_tA6237BF417AE52AD70CFB4EF24A7A82613DF9031* ___s_categoryForLatin1;
};
struct Type_t_StaticFields
{
	Binder_t91BFCE95A7057FADF4D8A1A342AFE52872246235* ___s_defaultBinder;
	Il2CppChar ___Delimiter;
	TypeU5BU5D_t97234E1129B564EB38B8D85CAC2AD8B5B9522FFB* ___EmptyTypes;
	RuntimeObject* ___Missing;
	MemberFilter_tF644F1AE82F611B677CE1964D5A3277DDA21D553* ___FilterAttribute;
	MemberFilter_tF644F1AE82F611B677CE1964D5A3277DDA21D553* ___FilterName;
	MemberFilter_tF644F1AE82F611B677CE1964D5A3277DDA21D553* ___FilterNameIgnoreCase;
};
#ifdef __clang__
#pragma clang diagnostic pop
#endif
struct ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918  : public RuntimeArray
{
	ALIGN_FIELD (8) RuntimeObject* m_Items[1];

	inline RuntimeObject* GetAt(il2cpp_array_size_t index) const
	{
		IL2CPP_ARRAY_BOUNDS_CHECK(index, (uint32_t)(this)->max_length);
		return m_Items[index];
	}
	inline RuntimeObject** GetAddressAt(il2cpp_array_size_t index)
	{
		IL2CPP_ARRAY_BOUNDS_CHECK(index, (uint32_t)(this)->max_length);
		return m_Items + index;
	}
	inline void SetAt(il2cpp_array_size_t index, RuntimeObject* value)
	{
		IL2CPP_ARRAY_BOUNDS_CHECK(index, (uint32_t)(this)->max_length);
		m_Items[index] = value;
		Il2CppCodeGenWriteBarrier((void**)m_Items + index, (void*)value);
	}
	inline RuntimeObject* GetAtUnchecked(il2cpp_array_size_t index) const
	{
		return m_Items[index];
	}
	inline RuntimeObject** GetAddressAtUnchecked(il2cpp_array_size_t index)
	{
		return m_Items + index;
	}
	inline void SetAtUnchecked(il2cpp_array_size_t index, RuntimeObject* value)
	{
		m_Items[index] = value;
		Il2CppCodeGenWriteBarrier((void**)m_Items + index, (void*)value);
	}
};


IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR bool Dictionary_2_ContainsKey_m703047C213F7AB55C9DC346596287773A1F670CD_gshared (Dictionary_2_t14FE4A752A83D53771C584E4C8D14E01F2AFD7BA* __this, RuntimeObject* ___0_key, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void Dictionary_2_set_Item_m1A840355E8EDAECEA9D0C6F5E51B248FAA449CBD_gshared (Dictionary_2_t14FE4A752A83D53771C584E4C8D14E01F2AFD7BA* __this, RuntimeObject* ___0_key, RuntimeObject* ___1_value, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void Dictionary_2_Add_m93FFFABE8FCE7FA9793F0915E2A8842C7CD0C0C1_gshared (Dictionary_2_t14FE4A752A83D53771C584E4C8D14E01F2AFD7BA* __this, RuntimeObject* ___0_key, RuntimeObject* ___1_value, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR RuntimeObject* Dictionary_2_get_Item_m4AAAECBE902A211BF2126E6AFA280AEF73A3E0D6_gshared (Dictionary_2_t14FE4A752A83D53771C584E4C8D14E01F2AFD7BA* __this, RuntimeObject* ___0_key, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void Dictionary_2__ctor_m5B32FBC624618211EB461D59CFBB10E987FD1329_gshared (Dictionary_2_t14FE4A752A83D53771C584E4C8D14E01F2AFD7BA* __this, const RuntimeMethod* method) ;

IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR Type_t* Object_GetType_mE10A8FC1E57F3DF29972CCBC026C2DC3942263B3 (RuntimeObject* __this, const RuntimeMethod* method) ;
inline bool Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* __this, Type_t* ___0_key, const RuntimeMethod* method)
{
	return ((  bool (*) (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE*, Type_t*, const RuntimeMethod*))Dictionary_2_ContainsKey_m703047C213F7AB55C9DC346596287773A1F670CD_gshared)(__this, ___0_key, method);
}
inline void Dictionary_2_set_Item_mDA78A8299D16DD1B42B93F0C63BE2D9CE92F8A00 (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* __this, Type_t* ___0_key, String_t* ___1_value, const RuntimeMethod* method)
{
	((  void (*) (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE*, Type_t*, String_t*, const RuntimeMethod*))Dictionary_2_set_Item_m1A840355E8EDAECEA9D0C6F5E51B248FAA449CBD_gshared)(__this, ___0_key, ___1_value, method);
}
inline void Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* __this, Type_t* ___0_key, String_t* ___1_value, const RuntimeMethod* method)
{
	((  void (*) (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE*, Type_t*, String_t*, const RuntimeMethod*))Dictionary_2_Add_m93FFFABE8FCE7FA9793F0915E2A8842C7CD0C0C1_gshared)(__this, ___0_key, ___1_value, method);
}
IL2CPP_MANAGED_FORCE_INLINE IL2CPP_METHOD_ATTR int32_t String_get_Length_m42625D67623FA5CC7A44D47425CE86FB946542D2_inline (String_t* __this, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR Il2CppChar String_get_Chars_mC49DF0CD2D3BE7BE97B3AD9C995BE3094F8E36D3 (String_t* __this, int32_t ___0_index, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void Random_InitState_mE70961834F42FFEEB06CB9C68175354E0C255664 (int32_t ___0_seed, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR float Random_Range_m5236C99A7D8AE6AC9190592DC66016652A2D2494 (float ___0_minInclusive, float ___1_maxInclusive, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void AIFLog_HsvToRgb_m8127559E2B9E12B0E73DDF7571D5840B5423A6E6 (double ___0_hue, double ___1_saturation, double ___2_value, int32_t* ___3_red, int32_t* ___4_green, int32_t* ___5_blue, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR String_t* String_Format_mA0534D6E2AE4D67A6BD8D45B3321323930EB930C (String_t* ___0_format, RuntimeObject* ___1_arg0, RuntimeObject* ___2_arg1, RuntimeObject* ___3_arg2, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR int32_t AIFLog_Clamp_mC7D4EE4D27E8092149E102845E0574051705BFF3 (int32_t ___0_i, const RuntimeMethod* method) ;
inline String_t* Dictionary_2_get_Item_m3359894DA1EF277B87D6220E9C380C4C01AE6008 (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* __this, Type_t* ___0_key, const RuntimeMethod* method)
{
	return ((  String_t* (*) (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE*, Type_t*, const RuntimeMethod*))Dictionary_2_get_Item_m4AAAECBE902A211BF2126E6AFA280AEF73A3E0D6_gshared)(__this, ___0_key, method);
}
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void Debug_LogFormat_mD555556327B42AA3482D077EFAEB16B0AFDF72C7 (String_t* ___0_format, ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* ___1_args, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR String_t* AIFLog_GenerateHexColorString_m8138E4FA059478B7BB9F063C8BDDDF166A7050E2 (RuntimeObject* ___0_obj, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR String_t* String_Format_m918500C1EFB475181349A79989BB79BB36102894 (String_t* ___0_format, ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* ___1_args, const RuntimeMethod* method) ;
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void AIFLog_Log_m72B8DE8424C4F242DBCC6C478DFAEE148873AA1B (RuntimeObject* ___0_obj, String_t* ___1_message, const RuntimeMethod* method) ;
inline void Dictionary_2__ctor_mFAF23CD29002CAB23492293F8C8B56962DE7A0B6 (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* __this, const RuntimeMethod* method)
{
	((  void (*) (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE*, const RuntimeMethod*))Dictionary_2__ctor_m5B32FBC624618211EB461D59CFBB10E987FD1329_gshared)(__this, method);
}
#ifdef __clang__
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Winvalid-offsetof"
#pragma clang diagnostic ignored "-Wunused-variable"
#endif
#ifdef __clang__
#pragma clang diagnostic pop
#endif
#ifdef __clang__
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Winvalid-offsetof"
#pragma clang diagnostic ignored "-Wunused-variable"
#endif
// Method Definition Index: 62430
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void AIFLog_SetColor_m4002E0003B45BC6913F898F8A56474DAC4CDC47F (RuntimeObject* ___0_obj, String_t* ___1_hexColorCode, const RuntimeMethod* method) 
{
	static bool s_Il2CppMethodInitialized;
	if (!s_Il2CppMethodInitialized)
	{
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC_RuntimeMethod_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F_RuntimeMethod_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2_set_Item_mDA78A8299D16DD1B42B93F0C63BE2D9CE92F8A00_RuntimeMethod_var);
		s_Il2CppMethodInitialized = true;
	}
	Type_t* V_0 = NULL;
	bool V_1 = false;
	{
		RuntimeObject* L_0 = ___0_obj;
		NullCheck(L_0);
		Type_t* L_1;
		L_1 = Object_GetType_mE10A8FC1E57F3DF29972CCBC026C2DC3942263B3(L_0, NULL);
		V_0 = L_1;
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* L_2 = ((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary;
		Type_t* L_3 = V_0;
		NullCheck(L_2);
		bool L_4;
		L_4 = Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F(L_2, L_3, Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F_RuntimeMethod_var);
		V_1 = L_4;
		bool L_5 = V_1;
		if (!L_5)
		{
			goto IL_0028;
		}
	}
	{
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* L_6 = ((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary;
		Type_t* L_7 = V_0;
		String_t* L_8 = ___1_hexColorCode;
		NullCheck(L_6);
		Dictionary_2_set_Item_mDA78A8299D16DD1B42B93F0C63BE2D9CE92F8A00(L_6, L_7, L_8, Dictionary_2_set_Item_mDA78A8299D16DD1B42B93F0C63BE2D9CE92F8A00_RuntimeMethod_var);
		goto IL_0037;
	}

IL_0028:
	{
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* L_9 = ((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary;
		Type_t* L_10 = V_0;
		String_t* L_11 = ___1_hexColorCode;
		NullCheck(L_9);
		Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC(L_9, L_10, L_11, Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC_RuntimeMethod_var);
	}

IL_0037:
	{
		return;
	}
}
// Method Definition Index: 62431
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR String_t* AIFLog_GenerateHexColorString_m8138E4FA059478B7BB9F063C8BDDDF166A7050E2 (RuntimeObject* ___0_obj, const RuntimeMethod* method) 
{
	static bool s_Il2CppMethodInitialized;
	if (!s_Il2CppMethodInitialized)
	{
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&_stringLiteral86953B386E543DC5AFB5CC6DFBD735EF7DAE369D);
		s_Il2CppMethodInitialized = true;
	}
	Type_t* V_0 = NULL;
	String_t* V_1 = NULL;
	int32_t V_2 = 0;
	int32_t V_3 = 0;
	double V_4 = 0.0;
	double V_5 = 0.0;
	double V_6 = 0.0;
	int32_t V_7 = 0;
	int32_t V_8 = 0;
	int32_t V_9 = 0;
	int32_t V_10 = 0;
	bool V_11 = false;
	String_t* V_12 = NULL;
	{
		RuntimeObject* L_0 = ___0_obj;
		NullCheck(L_0);
		Type_t* L_1;
		L_1 = Object_GetType_mE10A8FC1E57F3DF29972CCBC026C2DC3942263B3(L_0, NULL);
		V_0 = L_1;
		Type_t* L_2 = V_0;
		NullCheck(L_2);
		String_t* L_3;
		L_3 = VirtualFuncInvoker0< String_t* >::Invoke(8, L_2);
		V_1 = L_3;
		V_2 = 0;
		String_t* L_4 = V_1;
		NullCheck(L_4);
		int32_t L_5;
		L_5 = String_get_Length_m42625D67623FA5CC7A44D47425CE86FB946542D2_inline(L_4, NULL);
		V_3 = L_5;
		V_10 = 0;
		goto IL_0030;
	}

IL_001d:
	{
		int32_t L_6 = V_2;
		String_t* L_7 = V_1;
		int32_t L_8 = V_10;
		NullCheck(L_7);
		Il2CppChar L_9;
		L_9 = String_get_Chars_mC49DF0CD2D3BE7BE97B3AD9C995BE3094F8E36D3(L_7, L_8, NULL);
		V_2 = ((int32_t)il2cpp_codegen_add(L_6, (int32_t)L_9));
		int32_t L_10 = V_10;
		V_10 = ((int32_t)il2cpp_codegen_add(L_10, 1));
	}

IL_0030:
	{
		int32_t L_11 = V_10;
		int32_t L_12 = V_3;
		V_11 = (bool)((((int32_t)L_11) < ((int32_t)L_12))? 1 : 0);
		bool L_13 = V_11;
		if (L_13)
		{
			goto IL_001d;
		}
	}
	{
		int32_t L_14 = V_2;
		Random_InitState_mE70961834F42FFEEB06CB9C68175354E0C255664(L_14, NULL);
		float L_15;
		L_15 = Random_Range_m5236C99A7D8AE6AC9190592DC66016652A2D2494((0.0f), (360.0f), NULL);
		V_4 = ((double)L_15);
		float L_16;
		L_16 = Random_Range_m5236C99A7D8AE6AC9190592DC66016652A2D2494((0.0f), (1.0f), NULL);
		V_5 = ((double)L_16);
		V_6 = (1.0);
		double L_17 = V_4;
		double L_18 = V_5;
		double L_19 = V_6;
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		AIFLog_HsvToRgb_m8127559E2B9E12B0E73DDF7571D5840B5423A6E6(L_17, L_18, L_19, (&V_7), (&V_8), (&V_9), NULL);
		int32_t L_20 = V_7;
		int32_t L_21 = L_20;
		RuntimeObject* L_22 = Box(il2cpp_defaults.int32_class, &L_21);
		int32_t L_23 = V_8;
		int32_t L_24 = L_23;
		RuntimeObject* L_25 = Box(il2cpp_defaults.int32_class, &L_24);
		int32_t L_26 = V_9;
		int32_t L_27 = L_26;
		RuntimeObject* L_28 = Box(il2cpp_defaults.int32_class, &L_27);
		String_t* L_29;
		L_29 = String_Format_mA0534D6E2AE4D67A6BD8D45B3321323930EB930C(_stringLiteral86953B386E543DC5AFB5CC6DFBD735EF7DAE369D, L_22, L_25, L_28, NULL);
		V_12 = L_29;
		goto IL_00a6;
	}

IL_00a6:
	{
		String_t* L_30 = V_12;
		return L_30;
	}
}
// Method Definition Index: 62432
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void AIFLog_HsvToRgb_m8127559E2B9E12B0E73DDF7571D5840B5423A6E6 (double ___0_hue, double ___1_saturation, double ___2_value, int32_t* ___3_red, int32_t* ___4_green, int32_t* ___5_blue, const RuntimeMethod* method) 
{
	static bool s_Il2CppMethodInitialized;
	if (!s_Il2CppMethodInitialized)
	{
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Math_tEB65DE7CA8B083C412C969C92981C030865486CE_il2cpp_TypeInfo_var);
		s_Il2CppMethodInitialized = true;
	}
	double V_0 = 0.0;
	double V_1 = 0.0;
	double V_2 = 0.0;
	double V_3 = 0.0;
	bool V_4 = false;
	bool V_5 = false;
	bool V_6 = false;
	bool V_7 = false;
	double V_8 = 0.0;
	int32_t V_9 = 0;
	double V_10 = 0.0;
	double V_11 = 0.0;
	double V_12 = 0.0;
	double V_13 = 0.0;
	int32_t V_14 = 0;
	int32_t V_15 = 0;
	{
		double L_0 = ___0_hue;
		V_0 = L_0;
		goto IL_0013;
	}

IL_0005:
	{
		double L_1 = V_0;
		V_0 = ((double)il2cpp_codegen_add(L_1, (360.0)));
	}

IL_0013:
	{
		double L_2 = V_0;
		V_4 = (bool)((((double)L_2) < ((double)(0.0)))? 1 : 0);
		bool L_3 = V_4;
		if (L_3)
		{
			goto IL_0005;
		}
	}
	{
		goto IL_0036;
	}

IL_0028:
	{
		double L_4 = V_0;
		V_0 = ((double)il2cpp_codegen_subtract(L_4, (360.0)));
	}

IL_0036:
	{
		double L_5 = V_0;
		V_5 = (bool)((((int32_t)((!(((double)L_5) >= ((double)(360.0))))? 1 : 0)) == ((int32_t)0))? 1 : 0);
		bool L_6 = V_5;
		if (L_6)
		{
			goto IL_0028;
		}
	}
	{
		double L_7 = ___2_value;
		V_6 = (bool)((((int32_t)((!(((double)L_7) <= ((double)(0.0))))? 1 : 0)) == ((int32_t)0))? 1 : 0);
		bool L_8 = V_6;
		if (!L_8)
		{
			goto IL_0076;
		}
	}
	{
		double L_9 = (0.0);
		V_3 = L_9;
		double L_10 = L_9;
		V_2 = L_10;
		V_1 = L_10;
		goto IL_0181;
	}

IL_0076:
	{
		double L_11 = ___1_saturation;
		V_7 = (bool)((((int32_t)((!(((double)L_11) <= ((double)(0.0))))? 1 : 0)) == ((int32_t)0))? 1 : 0);
		bool L_12 = V_7;
		if (!L_12)
		{
			goto IL_0098;
		}
	}
	{
		double L_13 = ___2_value;
		double L_14 = L_13;
		V_3 = L_14;
		double L_15 = L_14;
		V_2 = L_15;
		V_1 = L_15;
		goto IL_0181;
	}

IL_0098:
	{
		double L_16 = V_0;
		V_8 = ((double)(L_16/(60.0)));
		double L_17 = V_8;
		il2cpp_codegen_runtime_class_init_inline(Math_tEB65DE7CA8B083C412C969C92981C030865486CE_il2cpp_TypeInfo_var);
		double L_18;
		L_18 = floor(L_17);
		V_9 = il2cpp_codegen_cast_double_to_int<int32_t>(L_18);
		double L_19 = V_8;
		int32_t L_20 = V_9;
		V_10 = ((double)il2cpp_codegen_subtract(L_19, ((double)L_20)));
		double L_21 = ___2_value;
		double L_22 = ___1_saturation;
		V_11 = ((double)il2cpp_codegen_multiply(L_21, ((double)il2cpp_codegen_subtract((1.0), L_22))));
		double L_23 = ___2_value;
		double L_24 = ___1_saturation;
		double L_25 = V_10;
		V_12 = ((double)il2cpp_codegen_multiply(L_23, ((double)il2cpp_codegen_subtract((1.0), ((double)il2cpp_codegen_multiply(L_24, L_25))))));
		double L_26 = ___2_value;
		double L_27 = ___1_saturation;
		double L_28 = V_10;
		V_13 = ((double)il2cpp_codegen_multiply(L_26, ((double)il2cpp_codegen_subtract((1.0), ((double)il2cpp_codegen_multiply(L_27, ((double)il2cpp_codegen_subtract((1.0), L_28))))))));
		int32_t L_29 = V_9;
		V_15 = L_29;
		int32_t L_30 = V_15;
		V_14 = L_30;
		int32_t L_31 = V_14;
		switch (((int32_t)il2cpp_codegen_subtract(L_31, (-1))))
		{
			case 0:
			{
				goto IL_016e;
			}
			case 1:
			{
				goto IL_0128;
			}
			case 2:
			{
				goto IL_0132;
			}
			case 3:
			{
				goto IL_013c;
			}
			case 4:
			{
				goto IL_0146;
			}
			case 5:
			{
				goto IL_0150;
			}
			case 6:
			{
				goto IL_015a;
			}
			case 7:
			{
				goto IL_0164;
			}
		}
	}
	{
		goto IL_0178;
	}

IL_0128:
	{
		double L_32 = ___2_value;
		V_1 = L_32;
		double L_33 = V_13;
		V_2 = L_33;
		double L_34 = V_11;
		V_3 = L_34;
		goto IL_0180;
	}

IL_0132:
	{
		double L_35 = V_12;
		V_1 = L_35;
		double L_36 = ___2_value;
		V_2 = L_36;
		double L_37 = V_11;
		V_3 = L_37;
		goto IL_0180;
	}

IL_013c:
	{
		double L_38 = V_11;
		V_1 = L_38;
		double L_39 = ___2_value;
		V_2 = L_39;
		double L_40 = V_13;
		V_3 = L_40;
		goto IL_0180;
	}

IL_0146:
	{
		double L_41 = V_11;
		V_1 = L_41;
		double L_42 = V_12;
		V_2 = L_42;
		double L_43 = ___2_value;
		V_3 = L_43;
		goto IL_0180;
	}

IL_0150:
	{
		double L_44 = V_13;
		V_1 = L_44;
		double L_45 = V_11;
		V_2 = L_45;
		double L_46 = ___2_value;
		V_3 = L_46;
		goto IL_0180;
	}

IL_015a:
	{
		double L_47 = ___2_value;
		V_1 = L_47;
		double L_48 = V_11;
		V_2 = L_48;
		double L_49 = V_12;
		V_3 = L_49;
		goto IL_0180;
	}

IL_0164:
	{
		double L_50 = ___2_value;
		V_1 = L_50;
		double L_51 = V_13;
		V_2 = L_51;
		double L_52 = V_11;
		V_3 = L_52;
		goto IL_0180;
	}

IL_016e:
	{
		double L_53 = ___2_value;
		V_1 = L_53;
		double L_54 = V_11;
		V_2 = L_54;
		double L_55 = V_12;
		V_3 = L_55;
		goto IL_0180;
	}

IL_0178:
	{
		double L_56 = ___2_value;
		double L_57 = L_56;
		V_3 = L_57;
		double L_58 = L_57;
		V_2 = L_58;
		V_1 = L_58;
		goto IL_0180;
	}

IL_0180:
	{
	}

IL_0181:
	{
		int32_t* L_59 = ___3_red;
		double L_60 = V_1;
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		int32_t L_61;
		L_61 = AIFLog_Clamp_mC7D4EE4D27E8092149E102845E0574051705BFF3(il2cpp_codegen_cast_double_to_int<int32_t>(((double)il2cpp_codegen_multiply(L_60, (255.0)))), NULL);
		*((int32_t*)L_59) = (int32_t)L_61;
		int32_t* L_62 = ___4_green;
		double L_63 = V_2;
		int32_t L_64;
		L_64 = AIFLog_Clamp_mC7D4EE4D27E8092149E102845E0574051705BFF3(il2cpp_codegen_cast_double_to_int<int32_t>(((double)il2cpp_codegen_multiply(L_63, (255.0)))), NULL);
		*((int32_t*)L_62) = (int32_t)L_64;
		int32_t* L_65 = ___5_blue;
		double L_66 = V_3;
		int32_t L_67;
		L_67 = AIFLog_Clamp_mC7D4EE4D27E8092149E102845E0574051705BFF3(il2cpp_codegen_cast_double_to_int<int32_t>(((double)il2cpp_codegen_multiply(L_66, (255.0)))), NULL);
		*((int32_t*)L_65) = (int32_t)L_67;
		return;
	}
}
// Method Definition Index: 62433
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR int32_t AIFLog_Clamp_mC7D4EE4D27E8092149E102845E0574051705BFF3 (int32_t ___0_i, const RuntimeMethod* method) 
{
	bool V_0 = false;
	int32_t V_1 = 0;
	bool V_2 = false;
	{
		int32_t L_0 = ___0_i;
		V_0 = (bool)((((int32_t)L_0) < ((int32_t)0))? 1 : 0);
		bool L_1 = V_0;
		if (!L_1)
		{
			goto IL_000d;
		}
	}
	{
		V_1 = 0;
		goto IL_0025;
	}

IL_000d:
	{
		int32_t L_2 = ___0_i;
		V_2 = (bool)((((int32_t)L_2) > ((int32_t)((int32_t)255)))? 1 : 0);
		bool L_3 = V_2;
		if (!L_3)
		{
			goto IL_0021;
		}
	}
	{
		V_1 = ((int32_t)255);
		goto IL_0025;
	}

IL_0021:
	{
		int32_t L_4 = ___0_i;
		V_1 = L_4;
		goto IL_0025;
	}

IL_0025:
	{
		int32_t L_5 = V_1;
		return L_5;
	}
}
// Method Definition Index: 62434
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void AIFLog_Log_m72B8DE8424C4F242DBCC6C478DFAEE148873AA1B (RuntimeObject* ___0_obj, String_t* ___1_message, const RuntimeMethod* method) 
{
	static bool s_Il2CppMethodInitialized;
	if (!s_Il2CppMethodInitialized)
	{
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Debug_t8394C7EEAECA3689C2C9B9DE9C7166D73596276F_il2cpp_TypeInfo_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC_RuntimeMethod_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F_RuntimeMethod_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2_get_Item_m3359894DA1EF277B87D6220E9C380C4C01AE6008_RuntimeMethod_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918_il2cpp_TypeInfo_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&_stringLiteral1A61CB167BC3EB3F99E232409244273D3BBED824);
		s_Il2CppMethodInitialized = true;
	}
	Type_t* V_0 = NULL;
	bool V_1 = false;
	String_t* V_2 = NULL;
	String_t* V_3 = NULL;
	{
		RuntimeObject* L_0 = ___0_obj;
		NullCheck(L_0);
		Type_t* L_1;
		L_1 = Object_GetType_mE10A8FC1E57F3DF29972CCBC026C2DC3942263B3(L_0, NULL);
		V_0 = L_1;
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* L_2 = ((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary;
		Type_t* L_3 = V_0;
		NullCheck(L_2);
		bool L_4;
		L_4 = Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F(L_2, L_3, Dictionary_2_ContainsKey_m5AF1FF54C84FB97FFB85E559036AB80013342C4F_RuntimeMethod_var);
		V_1 = L_4;
		bool L_5 = V_1;
		if (!L_5)
		{
			goto IL_004e;
		}
	}
	{
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* L_6 = ((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary;
		Type_t* L_7 = V_0;
		NullCheck(L_6);
		String_t* L_8;
		L_8 = Dictionary_2_get_Item_m3359894DA1EF277B87D6220E9C380C4C01AE6008(L_6, L_7, Dictionary_2_get_Item_m3359894DA1EF277B87D6220E9C380C4C01AE6008_RuntimeMethod_var);
		V_2 = L_8;
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_9 = (ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918*)(ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918*)SZArrayNew(ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918_il2cpp_TypeInfo_var, (uint32_t)3);
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_10 = L_9;
		String_t* L_11 = V_2;
		NullCheck(L_10);
		ArrayElementTypeCheck (L_10, L_11);
		(L_10)->SetAt(static_cast<il2cpp_array_size_t>(0), (RuntimeObject*)L_11);
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_12 = L_10;
		RuntimeObject* L_13 = ___0_obj;
		NullCheck(L_13);
		Type_t* L_14;
		L_14 = Object_GetType_mE10A8FC1E57F3DF29972CCBC026C2DC3942263B3(L_13, NULL);
		NullCheck(L_14);
		String_t* L_15;
		L_15 = VirtualFuncInvoker0< String_t* >::Invoke(8, L_14);
		NullCheck(L_12);
		ArrayElementTypeCheck (L_12, L_15);
		(L_12)->SetAt(static_cast<il2cpp_array_size_t>(1), (RuntimeObject*)L_15);
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_16 = L_12;
		String_t* L_17 = ___1_message;
		NullCheck(L_16);
		ArrayElementTypeCheck (L_16, L_17);
		(L_16)->SetAt(static_cast<il2cpp_array_size_t>(2), (RuntimeObject*)L_17);
		il2cpp_codegen_runtime_class_init_inline(Debug_t8394C7EEAECA3689C2C9B9DE9C7166D73596276F_il2cpp_TypeInfo_var);
		Debug_LogFormat_mD555556327B42AA3482D077EFAEB16B0AFDF72C7(_stringLiteral1A61CB167BC3EB3F99E232409244273D3BBED824, L_16, NULL);
		goto IL_008b;
	}

IL_004e:
	{
		RuntimeObject* L_18 = ___0_obj;
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		String_t* L_19;
		L_19 = AIFLog_GenerateHexColorString_m8138E4FA059478B7BB9F063C8BDDDF166A7050E2(L_18, NULL);
		V_3 = L_19;
		Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* L_20 = ((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary;
		Type_t* L_21 = V_0;
		String_t* L_22 = V_3;
		NullCheck(L_20);
		Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC(L_20, L_21, L_22, Dictionary_2_Add_m7371147962E855B8E8BE002A226B0EE34E37B0CC_RuntimeMethod_var);
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_23 = (ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918*)(ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918*)SZArrayNew(ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918_il2cpp_TypeInfo_var, (uint32_t)3);
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_24 = L_23;
		String_t* L_25 = V_3;
		NullCheck(L_24);
		ArrayElementTypeCheck (L_24, L_25);
		(L_24)->SetAt(static_cast<il2cpp_array_size_t>(0), (RuntimeObject*)L_25);
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_26 = L_24;
		RuntimeObject* L_27 = ___0_obj;
		NullCheck(L_27);
		Type_t* L_28;
		L_28 = Object_GetType_mE10A8FC1E57F3DF29972CCBC026C2DC3942263B3(L_27, NULL);
		NullCheck(L_28);
		String_t* L_29;
		L_29 = VirtualFuncInvoker0< String_t* >::Invoke(8, L_28);
		NullCheck(L_26);
		ArrayElementTypeCheck (L_26, L_29);
		(L_26)->SetAt(static_cast<il2cpp_array_size_t>(1), (RuntimeObject*)L_29);
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_30 = L_26;
		String_t* L_31 = ___1_message;
		NullCheck(L_30);
		ArrayElementTypeCheck (L_30, L_31);
		(L_30)->SetAt(static_cast<il2cpp_array_size_t>(2), (RuntimeObject*)L_31);
		il2cpp_codegen_runtime_class_init_inline(Debug_t8394C7EEAECA3689C2C9B9DE9C7166D73596276F_il2cpp_TypeInfo_var);
		Debug_LogFormat_mD555556327B42AA3482D077EFAEB16B0AFDF72C7(_stringLiteral1A61CB167BC3EB3F99E232409244273D3BBED824, L_30, NULL);
	}

IL_008b:
	{
		return;
	}
}
// Method Definition Index: 62435
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void AIFLog_LogFormat_m5422363988DE060F5C63FD17BC1D49C7CE4E8609 (RuntimeObject* ___0_obj, String_t* ___1_message, ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* ___2_args, const RuntimeMethod* method) 
{
	static bool s_Il2CppMethodInitialized;
	if (!s_Il2CppMethodInitialized)
	{
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		s_Il2CppMethodInitialized = true;
	}
	{
		RuntimeObject* L_0 = ___0_obj;
		String_t* L_1 = ___1_message;
		ObjectU5BU5D_t8061030B0A12A55D5AD8652A20C922FE99450918* L_2 = ___2_args;
		String_t* L_3;
		L_3 = String_Format_m918500C1EFB475181349A79989BB79BB36102894(L_1, L_2, NULL);
		il2cpp_codegen_runtime_class_init_inline(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		AIFLog_Log_m72B8DE8424C4F242DBCC6C478DFAEE148873AA1B(L_0, L_3, NULL);
		return;
	}
}
// Method Definition Index: 62436
IL2CPP_EXTERN_C IL2CPP_METHOD_ATTR void AIFLog__cctor_m4DC0AE75E92923C6232EDE2B32A26F61D1C0E136 (const RuntimeMethod* method) 
{
	static bool s_Il2CppMethodInitialized;
	if (!s_Il2CppMethodInitialized)
	{
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2__ctor_mFAF23CD29002CAB23492293F8C8B56962DE7A0B6_RuntimeMethod_var);
		il2cpp_codegen_initialize_runtime_metadata((uintptr_t*)&Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE_il2cpp_TypeInfo_var);
		s_Il2CppMethodInitialized = true;
	}
	{
		Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE* L_0 = (Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE*)il2cpp_codegen_object_new(Dictionary_2_tCAAF57FF731CF7E9CEC738A6E8400D208C1066EE_il2cpp_TypeInfo_var);
		Dictionary_2__ctor_mFAF23CD29002CAB23492293F8C8B56962DE7A0B6(L_0, Dictionary_2__ctor_mFAF23CD29002CAB23492293F8C8B56962DE7A0B6_RuntimeMethod_var);
		((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary = L_0;
		Il2CppCodeGenWriteBarrier((void**)(&((AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_StaticFields*)il2cpp_codegen_static_fields_for(AIFLog_t8B794DD93C6F51280325ED40ECC5B4CC8F8A956C_il2cpp_TypeInfo_var))->___typeColorDictionary), (void*)L_0);
		return;
	}
}
#ifdef __clang__
#pragma clang diagnostic pop
#endif
// Method Definition Index: 697
IL2CPP_MANAGED_FORCE_INLINE IL2CPP_METHOD_ATTR int32_t String_get_Length_m42625D67623FA5CC7A44D47425CE86FB946542D2_inline (String_t* __this, const RuntimeMethod* method) 
{
	{
		int32_t L_0 = __this->____stringLength;
		return L_0;
	}
}

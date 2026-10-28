ARCHS = arm64
MOD_NAME ?= AppMod
MOD_SDK ?= 16.5
MOD_MIN_IOS ?= 15.0
MOD_CXX_STANDARD ?= c++2b
TARGET = iphone:clang:$(MOD_SDK):$(MOD_MIN_IOS)
THEOS ?= $(HOME)/theos
include $(THEOS)/makefiles/common.mk
LIBRARY_NAME = $(MOD_NAME)
$(MOD_NAME)_FILES = Mod.mm RuntimeHooks.mm Credits.m AdDisabler.m
$(MOD_NAME)_FRAMEWORKS = Foundation UIKit
$(MOD_NAME)_CFLAGS = -fobjc-arc -Wall -Wextra -Wno-unused-parameter
$(MOD_NAME)_CCFLAGS = -std=$(MOD_CXX_STANDARD) -Wall -Wextra
$(MOD_NAME)_LDFLAGS = -Wl,-install_name,@executable_path/Frameworks/$(MOD_NAME).dylib
include $(THEOS_MAKE_PATH)/library.mk

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <string.h>
#import <mach-o/dyld.h>

static BOOL DisabledReady(id rSelf, SEL eSelector)
{
    return NO;
}

static void DisabledAction(id rSelf, SEL eSelector)
{
}

static void DisabledActionOne(id rSelf, SEL eSelector, id rValue)
{
}

static void DisabledActionTwo(id rSelf, SEL eSelector, id rFirst, id rSecond)
{
}

static void DisabledActionThree(id rSelf, SEL eSelector, id rFirst, id rSecond, id rThird)
{
}

static void HiddenBanner(id rSelf, SEL eSelector, BOOL bHidden)
{
    ((void (*)(id, SEL, BOOL))class_getMethodImplementation([UIView class], eSelector))(rSelf, eSelector, YES);
}

static void InvisibleBanner(id rSelf, SEL eSelector, CGFloat dAlpha)
{
    ((void (*)(id, SEL, CGFloat))class_getMethodImplementation([UIView class], eSelector))(rSelf, eSelector, 0);
}

static void DisabledAutoload(id rSelf, SEL eSelector, BOOL bAutoload)
{
}

static BOOL Replace(Class clTarget, const char *szSelector, IMP pReplacement, const char *szTypes)
{
    SEL eSelector = sel_registerName(szSelector);
    Method hMethod = class_getInstanceMethod(clTarget, eSelector);
    if (!hMethod || strcmp(method_getTypeEncoding(hMethod), szTypes) != 0)
        return NO;
    class_replaceMethod(clTarget, eSelector, pReplacement, method_getTypeEncoding(hMethod));
    return YES;
}

static BOOL DisabledReadyTwo(id rSelf, SEL eSelector, id rFirst, id rSecond)
{
    return NO;
}

static BOOL DisabledReadyThree(id rSelf, SEL eSelector, id rFirst, id rSecond, id rThird)
{
    return NO;
}

static id DisabledShowThree(id rSelf, SEL eSelector, id rFirst, id rSecond, id rThird)
{
    return nil;
}

static id DisabledShowFour(id rSelf, SEL eSelector, id rFirst, id rSecond, id rThird, id rFourth)
{
    return nil;
}

static void InstallLearningsHooks(void)
{
    static BOOL s_bInstalled = NO;
    Class clTarget = objc_getMetaClass("_TtC15LearningsAdsKit8MeeviiAd");
    if (!clTarget || s_bInstalled)
        return;
    s_bInstalled = YES;
    unsigned int uHooks = 0;
    uHooks += Replace(clTarget, "loadAd:", (IMP)DisabledActionOne, "v24@0:8@16");
    uHooks += Replace(clTarget, "isReadyForPlacement:position:showId:", (IMP)DisabledReadyThree, "B40@0:8@16@24@32");
    uHooks += Replace(clTarget, "isValidForPlacement:position:", (IMP)DisabledReadyTwo, "B32@0:8@16@24");
    uHooks += Replace(clTarget, "showAd:fromViewController:position:showId:", (IMP)DisabledShowFour, "@48@0:8@16@24@32@40");
    uHooks += Replace(clTarget, "showBanner:inContainer:position:", (IMP)DisabledShowThree, "@40@0:8@16@24@32");
    uHooks += Replace(clTarget, "showNativeAd:inContainer:position:showId:", (IMP)DisabledShowFour, "@48@0:8@16@24@32@40");
    NSLog(@"[ColoreverMod] Installed %u/6 Learnings ad hooks.", uHooks);
}

static void ImageAdded(const struct mach_header *pstHeader, intptr_t lSlide)
{
    dispatch_async(dispatch_get_main_queue(), ^{
        InstallLearningsHooks();
    });
}

__attribute__((constructor)) static void InitializeAdDisabler(void)
{
    @autoreleasepool
    {
        InstallLearningsHooks();
        _dyld_register_func_for_add_image(ImageAdded);
        if (!dlopen("@executable_path/Frameworks/AppLovinSDK.framework/AppLovinSDK", RTLD_NOW | RTLD_GLOBAL))
        {
            NSLog(@"[ColoreverMod] Cannot load AppLovinSDK: %s", dlerror());
            return;
        }
        unsigned int uHooks = 0;
        const char *aClasses[] = { "MAInterstitialAd", "MAAppOpenAd", "MARewardedAd" };
        for (unsigned int uIndex = 0; uIndex < sizeof(aClasses) / sizeof(aClasses[0]); ++uIndex)
        {
            Class clTarget = objc_getClass(aClasses[uIndex]);
            if (!clTarget)
                continue;
            uHooks += Replace(clTarget, "isReady", (IMP)DisabledReady, "B16@0:8");
            uHooks += Replace(clTarget, "loadAd", (IMP)DisabledAction, "v16@0:8");
            uHooks += Replace(clTarget, "showAd", (IMP)DisabledAction, "v16@0:8");
            uHooks += Replace(clTarget, "showAdForPlacement:", (IMP)DisabledActionOne, "v24@0:8@16");
            uHooks += Replace(clTarget, "showAdForPlacement:customData:", (IMP)DisabledActionTwo, "v32@0:8@16@24");
            uHooks += Replace(clTarget, "showAdForPlacement:customData:viewController:", (IMP)DisabledActionThree, "v40@0:8@16@24@32");
        }
        Class clBanner = objc_getClass("MAAdView");
        if (clBanner)
        {
            uHooks += Replace(clBanner, "loadAd", (IMP)DisabledAction, "v16@0:8");
            uHooks += Replace(clBanner, "startAutoRefresh", (IMP)DisabledAction, "v16@0:8");
            uHooks += Replace(clBanner, "autoload", (IMP)DisabledReady, "B16@0:8");
            uHooks += Replace(clBanner, "setAutoload:", (IMP)DisabledAutoload, "v20@0:8B16");
            uHooks += Replace(clBanner, "setHidden:", (IMP)HiddenBanner, "v20@0:8B16");
            uHooks += Replace(clBanner, "setAlpha:", (IMP)InvisibleBanner, "v24@0:8d16");
        }
        Class clNative = objc_getClass("MANativeAdLoader");
        if (clNative)
        {
            uHooks += Replace(clNative, "loadAd", (IMP)DisabledAction, "v16@0:8");
            uHooks += Replace(clNative, "loadAdIntoAdView:", (IMP)DisabledActionOne, "v24@0:8@16");
            uHooks += Replace(clNative, "renderNativeAdView:withAd:", (IMP)DisabledReadyTwo, "B32@0:8@16@24");
        }
        NSLog(@"[ColoreverMod] Installed %u MAX ad hooks.", uHooks);
    }
}

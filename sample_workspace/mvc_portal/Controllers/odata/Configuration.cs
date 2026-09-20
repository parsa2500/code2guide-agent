using Microsoft.AspNet.OData.Builder;
using Microsoft.AspNet.OData.Extensions;
using System.Web.Http;

namespace SampleMvcPortal.Controllers.odata
{
    public static class ODataConfig
    {
        public static void Register(HttpConfiguration config)
        {
            var builder = new ODataConventionModelBuilder();
            builder.EntitySet<object>("contracts");
            config.MapODataServiceRoute(
                routeName: "odata",
                routePrefix: "odata/",
                model: builder.GetEdmModel()
            );
        }
    }
}

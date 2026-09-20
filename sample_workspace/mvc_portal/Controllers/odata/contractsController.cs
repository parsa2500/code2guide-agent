using System.Linq;
using Microsoft.AspNet.OData;

namespace SampleMvcPortal.Controllers.odata
{
    public class contractsController : ODataController
    {
        [EnableQuery]
        public IQueryable<object> GetContracts()
        {
            return Enumerable.Empty<object>().AsQueryable();
        }
    }
}
